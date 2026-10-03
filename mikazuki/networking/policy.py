"""统一代理解析。镜像选择与传输代理正交；显式代理失败不静默退回直连。"""
from __future__ import annotations

from dataclasses import dataclass, field
from contextlib import contextmanager
from contextvars import ContextVar
from fnmatch import fnmatchcase
import ipaddress
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

MODES = {"auto", "system", "manual", "direct"}
LOOPBACK = "localhost,127.0.0.1,::1"
_PROXY_KEYS = {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}
_active_policy = ContextVar("active_network_policy", default=None)
_startup_proxy_env: dict | None = None
ORIGINAL_PROXY_ENV = "NEXT_TRAINER_ORIGINAL_PROXY_ENV"


def original_proxy_env(env: dict) -> dict:
    raw = env.get(ORIGINAL_PROXY_ENV)
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {k: v for k, v in parsed.items() if k.lower() in _PROXY_KEYS and isinstance(v, str)}
        except ValueError:
            pass
    return {k: v for k, v in env.items() if k.lower() in _PROXY_KEYS}


def initialize_sdk_environment():
    """One-time SDK compatibility env; resolver keeps the ORIGINAL inputs.

    Otherwise switching saved manual settings back to auto would mistakenly
    treat our own injected proxy as an operator-provided environment override.
    """
    global _startup_proxy_env
    policy = resolve_policy()
    if _startup_proxy_env is None:
        _startup_proxy_env = original_proxy_env(dict(os.environ))
    env = policy.process_env()
    for key in list(os.environ):
        if key.lower() in _PROXY_KEYS:
            del os.environ[key]
    os.environ.update(env)


@contextmanager
def task_policy():
    """Freeze routing for one task; future tasks pick up saved changes."""
    policy = resolve_policy()
    token = _active_policy.set(policy)
    try:
        yield policy
    finally:
        _active_policy.reset(token)


def redact(value: object) -> str:
    # Strip URL credentials AND query strings (signed URLs can contain tokens).
    return re.sub(r"https?://[^\s\"'<>]+", _safe_url, str(value))


def _safe_url(match) -> str:
    try:
        url = urlsplit(match.group(0))
        host = url.hostname or ""
        host = f"[{host}]" if ":" in host else host
        return f"{url.scheme}://{host}" + (f":{url.port}" if url.port else "") + url.path
    except ValueError:
        return "<redacted-url>"


def proxy_url(value: str | None) -> str | None:
    if not value:
        return None
    value = str(value).strip()
    if "://" not in value:
        value = "http://" + value
    try:
        url = urlsplit(value)
        valid = (url.scheme in {"http", "https"} and url.hostname and (url.port is None or url.port > 0)
                 and url.path in {"", "/"} and not url.query and not url.fragment
                 and not any(c.isspace() for c in value))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("代理需要有效的 HTTP/HTTPS 地址与端口；SOCKS 请改用代理软件的 HTTP 端口。")
    return value.rstrip("/")


def system_settings() -> dict:
    if os.name != "nt":
        return {}
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as key:
            def read(name, default=""):
                try:
                    return winreg.QueryValueEx(key, name)[0]
                except OSError:
                    return default
            result = {"pac": bool(read("AutoConfigURL")), "no_proxy": str(read("ProxyOverride"))}
            if not read("ProxyEnable", 0):
                return result
            server = str(read("ProxyServer")).strip()
            if "=" in server:
                for part in server.split(";"):
                    scheme, sep, address = part.partition("=")
                    if sep and scheme.strip().lower() in {"http", "https"}:
                        result[scheme.strip().lower()] = address.strip()
            elif server:
                result.update(http=server, https=server)
            return result
    except OSError:
        return {}


def config_path() -> Path:
    return Path(os.environ.get("NEXT_TRAINER_NETWORK_CONFIG", "config/network.local.json"))


def load_settings() -> dict:
    path = config_path()
    if not path.is_file():
        return {}
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(settings, dict):
            raise ValueError()
        return settings
    except (OSError, ValueError):
        raise ValueError("网络设置文件无效，请修复 config/network.local.json。") from None


@dataclass(frozen=True)
class NetworkPolicy:
    mode: str = "auto"
    http_proxy: str | None = field(default=None, repr=False)
    https_proxy: str | None = field(default=None, repr=False)
    no_proxy: str = LOOPBACK
    source: str = "direct"
    warning: str = ""

    def bypass(self, url: str) -> bool:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        try:
            address = ipaddress.ip_address(host)
            if address.is_loopback:
                return True
        except ValueError:
            address = None
        if host == "localhost":
            return True
        for token in self.no_proxy.replace(";", ",").split(","):
            token = token.strip().lower()
            if not token:
                continue
            if token == "*" or (token == "<local>" and "." not in host and address is None):
                return True
            if "/" in token:
                try:
                    if address and address in ipaddress.ip_network(token, strict=False):
                        return True
                except ValueError:
                    pass
                continue
            if token.count(":") == 1 and token.rsplit(":", 1)[1].isdigit():
                token, port = token.rsplit(":", 1)
                if int(port) != (parsed.port or (443 if parsed.scheme == "https" else 80)):
                    continue
            token = token.strip("[]").lstrip(".")
            if host == token or host.endswith("." + token) or fnmatchcase(host, token):
                return True
        return False

    def proxy_for(self, url: str) -> str | None:
        if self.mode == "direct" or self.bypass(url):
            return None
        return self.https_proxy if urlsplit(url).scheme == "https" else self.http_proxy

    def process_env(self, base: dict | None = None) -> dict[str, str]:
        env = dict(os.environ if base is None else base)
        for key in list(env):
            if key.lower() in _PROXY_KEYS:
                del env[key]
        for key, value in (("http_proxy", self.http_proxy), ("https_proxy", self.https_proxy), ("no_proxy", self.no_proxy)):
            if value and (self.mode != "direct" or key == "no_proxy"):
                env[key] = env[key.upper()] = value
        return env

    def diagnostic(self, url: str | None = None) -> dict:
        return {
            "network_mode": self.mode, "source": self.source,
            "http_proxy": redact(self.http_proxy or ""), "https_proxy": redact(self.https_proxy or ""),
            "no_proxy": self.no_proxy, "warning": self.warning,
            "proxy_enabled": bool(self.proxy_for(url)) if url else bool(self.http_proxy or self.https_proxy),
        }


def resolve_policy(overrides: dict | None = None, *, environ: dict | None = None,
                   saved: dict | None = None, system: dict | None = None) -> NetworkPolicy:
    active = _active_policy.get()
    if active is not None and all(value is None for value in (overrides, environ, saved, system)):
        return active
    env = dict(os.environ if environ is None else environ)
    if environ is None and (_startup_proxy_env is not None or ORIGINAL_PROXY_ENV in env):
        original = _startup_proxy_env if _startup_proxy_env is not None else original_proxy_env(env)
        env = {k: v for k, v in env.items() if k.lower() not in _PROXY_KEYS}
        env.update(original)
    settings = dict(load_settings() if saved is None else saved)
    settings.update({k: v for k, v in (overrides or {}).items() if v is not None})
    mode = settings.get("mode") or env.get("NEXT_TRAINER_NETWORK_MODE", "auto")
    if mode not in MODES:
        raise ValueError("网络模式必须是 auto/system/manual/direct。")
    def variable(name):
        # A present empty variable explicitly disables that protocol.
        return env.get(name.lower(), env.get(name.upper()))
    no_proxy = settings.get("no_proxy", variable("no_proxy"))
    if mode == "direct":
        return NetworkPolicy(mode=mode, no_proxy="*", source="direct")
    system = system_settings() if system is None else system
    if mode == "manual":
        http = settings.get("http_proxy") or settings.get("https_proxy")
        https = settings.get("https_proxy") or settings.get("http_proxy")
        if not (http or https):
            raise ValueError("手动模式需要代理地址。")
        source = "manual"
    elif mode == "system":
        http, https = system.get("http"), system.get("https")
        source = "system"
    else:
        http = settings.get("http_proxy", variable("http_proxy"))
        https = settings.get("https_proxy", variable("https_proxy"))
        all_proxy = variable("all_proxy")
        has_environment_proxy = http is not None or https is not None or all_proxy is not None
        source = "environment" if has_environment_proxy else "system"
        http = http if http is not None else (all_proxy if all_proxy is not None else system.get("http"))
        https = https if https is not None else (all_proxy if all_proxy is not None else system.get("https"))
    bypass = no_proxy if no_proxy is not None else system.get("no_proxy", "")
    bypass = ",".join(dict.fromkeys((str(bypass).replace(";", ",") + "," + LOOPBACK).split(",")))
    http, https = proxy_url(http), proxy_url(https)
    warning = "检测到 PAC，当前不执行 PAC 脚本；请设置手动代理。" if system.get("pac") and not (http or https) else ""
    return NetworkPolicy(mode, http, https, bypass, source if http or https else "direct", warning)

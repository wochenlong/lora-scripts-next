import ipaddress
import secrets
from typing import FrozenSet
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field, SecretStr, root_validator, validator


_RUN_TOKEN_HEADER = "x-nexttrainer-run-token"
_FORBIDDEN_DETAIL = "AGENT_ROUTE_FORBIDDEN"


def _is_loopback_host(value: str) -> bool:
    if value.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def _raise_forbidden(reason: str) -> None:
    raise HTTPException(
        status_code=403,
        detail={"code": _FORBIDDEN_DETAIL, "reason": reason},
    )


class AgentRouteAuthorityConfig(BaseModel):
    """Immutable browser authority expected by optional Agent routes.

    The values are supplied by the host at application startup. They are
    intentionally exact strings: validation must not broaden a configured
    authority through aliases, wildcard origins, or implicit default ports.
    """

    allowed_hosts: FrozenSet[str] = Field(..., min_items=1)
    allowed_origins: FrozenSet[str] = Field(..., min_items=1)
    run_token: SecretStr

    @validator("allowed_hosts", pre=True)
    def validate_allowed_hosts(cls, value):
        hosts = frozenset(value or ())
        for host in hosts:
            if not isinstance(host, str) or not host or host != host.strip():
                raise ValueError("allowed_hosts must contain exact non-empty strings")
            if any(marker in host for marker in ("//", "/", "?", "#", "@", ",")):
                raise ValueError("allowed_hosts must contain Host header values, not URLs")
            parsed = urlsplit(f"//{host}")
            if not parsed.hostname or not _is_loopback_host(parsed.hostname):
                raise ValueError("allowed_hosts must resolve to an explicit loopback host")
        return hosts

    @validator("allowed_origins", pre=True)
    def validate_allowed_origins(cls, value):
        origins = frozenset(value or ())
        for origin in origins:
            if not isinstance(origin, str) or not origin or origin != origin.strip() or origin == "*":
                raise ValueError("allowed_origins must contain exact non-wildcard origins")
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
                or not parsed.hostname
                or not _is_loopback_host(parsed.hostname)
            ):
                raise ValueError("allowed_origins must contain loopback HTTP origins only")
            if parsed.path == "/":
                raise ValueError("allowed_origins must not contain a trailing path separator")
        return origins

    @validator("run_token")
    def validate_run_token(cls, value: SecretStr):
        if len(value.get_secret_value()) < 16:
            raise ValueError("run_token must contain at least 16 characters")
        return value

    @root_validator
    def origins_must_match_allowed_hosts(cls, values):
        hosts = values.get("allowed_hosts") or frozenset()
        for origin in values.get("allowed_origins") or frozenset():
            if urlsplit(origin).netloc not in hosts:
                raise ValueError("every allowed origin must exactly match an allowed Host value")
        return values

    class Config:
        allow_mutation = False


class AgentRouteAuthorityContext(BaseModel):
    host: str
    origin: str | None
    client_host: str

    class Config:
        allow_mutation = False


class AgentRouteAuthority:
    """FastAPI dependency enforcing the browser-to-Agent authority boundary.

    Use :meth:`for_json_mutation` on JSON mutation routes and
    :meth:`for_stream` on SSE/stream routes. A route dependency is deliberately
    separate from Agent/Pi routing so the generic plugin host can be tested and
    reused without importing optional plugin code.
    """

    def __init__(
        self,
        config: AgentRouteAuthorityConfig,
        *,
        require_origin: bool,
        require_json: bool,
    ) -> None:
        self._config = config
        self._require_origin = require_origin
        self._require_json = require_json

    @classmethod
    def for_json_mutation(cls, config: AgentRouteAuthorityConfig) -> "AgentRouteAuthority":
        return cls(config, require_origin=True, require_json=True)

    @classmethod
    def for_stream(cls, config: AgentRouteAuthorityConfig) -> "AgentRouteAuthority":
        return cls(config, require_origin=True, require_json=False)

    @classmethod
    def for_read(cls, config: AgentRouteAuthorityConfig) -> "AgentRouteAuthority":
        return cls(config, require_origin=False, require_json=False)

    async def __call__(self, request: Request) -> AgentRouteAuthorityContext:
        client_host = request.client.host if request.client is not None else ""
        if not _is_loopback_host(client_host):
            _raise_forbidden("loopback")

        host = request.headers.get("host", "")
        if host not in self._config.allowed_hosts:
            _raise_forbidden("host")

        sec_fetch_site = request.headers.get("sec-fetch-site")
        if sec_fetch_site is not None and sec_fetch_site.strip().casefold() == "cross-site":
            _raise_forbidden("cross-site")

        origin = request.headers.get("origin")
        if self._require_origin and origin not in self._config.allowed_origins:
            _raise_forbidden("origin")
        if origin is not None and origin not in self._config.allowed_origins:
            _raise_forbidden("origin")

        if self._require_json:
            media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
            if media_type != "application/json":
                _raise_forbidden("content-type")

        supplied_token = request.headers.get(_RUN_TOKEN_HEADER, "")
        expected_token = self._config.run_token.get_secret_value()
        if not supplied_token or not secrets.compare_digest(supplied_token, expected_token):
            _raise_forbidden("run-token")

        return AgentRouteAuthorityContext(host=host, origin=origin, client_host=client_host)


__all__ = [
    "AgentRouteAuthority",
    "AgentRouteAuthorityConfig",
    "AgentRouteAuthorityContext",
]

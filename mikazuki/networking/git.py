"""Recoverable pinned Git source acquisition; never deletes a user's checkout."""
from __future__ import annotations

from collections import deque
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time

from .policy import NetworkPolicy, resolve_policy, redact

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


class GitDownloadError(RuntimeError):
    pass


class GitDownloadAdapter:
    def __init__(self, policy: NetworkPolicy | None = None, log=None, *, attempts=3, timeout=300):
        self.policy = policy or resolve_policy()
        self.log = log or (lambda line: None)
        self.attempts, self.timeout = attempts, timeout

    def run(self, args: list[str], *, url: str | None = None, retry=False) -> str:
        env = self.policy.process_env()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["LC_ALL"] = "C"
        # Override any global/URL-specific Git proxy without persisting config
        # or exposing credentials in the process command line.
        if url and urlsplit_scheme(url) in {"http", "https"}:
            count = int(env.get("GIT_CONFIG_COUNT", "0"))
            for key, value in ((f"http.{url}.proxy", self.policy.proxy_for(url) or ""),
                               ("http.lowSpeedLimit", "1024"), ("http.lowSpeedTime", "60")):
                env[f"GIT_CONFIG_KEY_{count}"] = key
                env[f"GIT_CONFIG_VALUE_{count}"] = value
                count += 1
            env["GIT_CONFIG_COUNT"] = str(count)
            self.log(f"[network] {self.policy.diagnostic(url)}")
        limit = self.attempts if retry else 1
        for attempt in range(1, limit + 1):
            self.log(f"[git] attempt={attempt}/{limit} {redact(' '.join(args))}")
            output: queue.Queue = queue.Queue()
            tail: deque[str] = deque(maxlen=60)
            process = subprocess.Popen(["git", *args], env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            def pump():
                try:
                    for line in process.stdout:
                        output.put(line)
                finally:
                    output.put(None)
            reader = threading.Thread(target=pump, daemon=True)
            reader.start()
            last = time.monotonic()
            timed_out = False
            try:
                while True:
                    try:
                        line = output.get(timeout=min(1, self.timeout))
                    except queue.Empty:
                        if time.monotonic() - last < self.timeout:
                            continue
                        timed_out = True
                        break
                    if line is None:
                        break
                    last = time.monotonic()
                    line = redact(line.rstrip())
                    tail.append(line)
                    self.log(line)
            finally:
                if not timed_out:
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        timed_out = True
                if process.poll() is None:
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
                    else:
                        process.kill()
                code = process.wait()
                reader.join(timeout=5)
                process.stdout.close()
            message = "\n".join(tail)
            if code == 0 and not timed_out:
                return message
            transient = timed_out or bool(re.search(
                r"connection (?:reset|timed out)|timed? out|could not resolve|couldn't connect|failed to connect|early eof|remote end hung up|HTTP [25]|error: (?:500|502|503|504)|returned error: (?:429|500|502|503|504)",
                message, re.I))
            if attempt == limit or not transient:
                raise GitDownloadError(f"Git {'网络超时' if timed_out else '命令失败'}: {message[-2000:]}") from None
            self.log(f"[retry] transient transport error; delay={2 ** (attempt - 1)}s")
            time.sleep(2 ** (attempt - 1))
        raise AssertionError("unreachable")

    def acquire(self, target: Path, url: str, commit: str | None, valid) -> Path:
        if commit and not re.fullmatch(r"[0-9a-fA-F]{7,40}", commit):
            raise GitDownloadError("source_commit 必须是 Git 提交哈希。")
        if urlsplit_scheme(url) not in {"http", "https", "file"}:
            raise GitDownloadError("源码地址必须为 HTTP/HTTPS URL 或受控本地 file URL。")
        target = target.resolve()
        # A lock serializes tasks sharing the same cache. No recursive removal.
        with _locks_guard:
            lock = _locks.setdefault(str(target), threading.Lock())
        with lock:
            if target.exists() and not (target / ".git").is_dir():
                if any(target.iterdir()):
                    raise GitDownloadError(f"缓存目录不是 Git 仓库，请保留并检查: {target}")
            target.mkdir(parents=True, exist_ok=True)
            if not (target / ".git").is_dir():
                self.run(["init", str(target)])
            prefix = ["-C", str(target)]
            head = self.run([*prefix, "status", "--porcelain"])
            if head:
                raise GitDownloadError("源码缓存存在本地修改，请先保留修改后重试。")
            if commit and valid(target):
                # Existing pinned object: use it offline, no network needed.
                present = subprocess.run(["git", *prefix, "cat-file", "-e", commit + "^{commit}"],
                                         capture_output=True)
                if present.returncode == 0:
                    self.log("[source] cache=hit")
                    return target
            # Fetch from the currently resolved URL; never overwrite origin.
            ref = commit or "HEAD"
            self.run([*prefix, "fetch", "--progress", "--depth", "1", url, ref], url=url, retry=True)
            fetched = self.run([*prefix, "rev-parse", "FETCH_HEAD"]).strip()
            if commit and not fetched.lower().startswith(commit.lower()):
                raise GitDownloadError("获取的提交与 source_commit 不一致。")
            self.run([*prefix, "checkout", "--detach", fetched])
            if not valid(target):
                raise GitDownloadError("获取的源码缺少引擎所需文件。")
            return target


def urlsplit_scheme(url):
    from urllib.parse import urlsplit
    return urlsplit(url).scheme

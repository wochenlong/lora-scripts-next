from __future__ import annotations

import json
import subprocess
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

import pytest
from mikazuki.networking.policy import NetworkPolicy, resolve_policy, redact, proxy_url
from mikazuki.networking.http import HttpDownloadAdapter
from mikazuki.networking.git import GitDownloadAdapter, GitDownloadError


def test_no_proxy_alone_does_not_mask_system():
    p = resolve_policy(saved={}, environ={"NO_PROXY": "example.org"},
                       system={"http": "127.0.0.1:7890", "https": "127.0.0.1:7890"})
    assert p.https_proxy == "http://127.0.0.1:7890"
    assert p.bypass("https://example.org/")
    assert p.proxy_for("https://github.com/") == p.https_proxy


def test_env_precedence_and_direct_scrubs_all_aliases():
    env = {"HTTPS_PROXY": "http://env:8080", "ALL_PROXY": "http://all:8081", "PATH": "kept"}
    p = resolve_policy(saved={}, environ=env, system={"https": "system:80"})
    assert p.https_proxy == "http://env:8080"
    assert p.http_proxy == "http://all:8081"
    direct = resolve_policy(saved={"mode": "direct"}, environ=env)
    result = direct.process_env(env)
    assert not any(k.lower() in {"https_proxy", "http_proxy", "all_proxy"} for k in result)
    assert result["PATH"] == "kept"


def test_manual_system_and_pac_are_distinct():
    p = resolve_policy(saved={"mode": "system"}, environ={"HTTPS_PROXY": "http://env:80"}, system={"https": "system:81"})
    assert p.https_proxy == "http://system:81"
    p = resolve_policy(saved={"mode": "manual", "http_proxy": "manual:82"}, environ={}, system={})
    assert p.https_proxy == "http://manual:82"
    p = resolve_policy(saved={}, environ={}, system={"pac": True})
    assert p.warning and not p.https_proxy
    with pytest.raises(ValueError):
        resolve_policy(saved={"mode": "manual"}, environ={}, system={})


@pytest.mark.parametrize("url", ["http://localhost:100/", "http://127.0.0.2/", "http://[::1]/", "https://sub.example.org/", "http://10.2.3.4/", "http://intranet/", "https://only.test:8443/"])
def test_bypass_rules(url):
    p = NetworkPolicy(no_proxy=".example.org,10.0.0.0/8,<local>,only.test:8443")
    assert p.bypass(url)
    assert not p.bypass("https://notexample.org")
    assert not p.bypass("https://only.test:443")


def test_credential_redaction_and_proxy_validation():
    assert redact("https://user:secret@host:443/pkg?token=secret") == "https://host:443/pkg"
    assert "secret" not in repr(NetworkPolicy(https_proxy="http://user:secret@host:80"))
    assert proxy_url("localhost:7890") == "http://localhost:7890"
    with pytest.raises(ValueError):
        proxy_url("socks5://localhost:7890")


def test_registry_missing_override_keeps_proxy(monkeypatch):
    winreg = pytest.importorskip("winreg")
    import mikazuki.networking.policy as mod
    class Key:
        def __enter__(self): return self
        def __exit__(self, *a): pass
    def query(key, name):
        if name not in {"ProxyEnable", "ProxyServer"}: raise FileNotFoundError()
        return ({"ProxyEnable": 1, "ProxyServer": "http=localhost:7890;https=localhost:7891"}[name], 1)
    monkeypatch.setattr(winreg, "OpenKey", lambda *a: Key())
    monkeypatch.setattr(winreg, "QueryValueEx", query)
    assert mod.system_settings()["https"] == "localhost:7891"


def test_http_proxy_routes_and_redirect_bypasses_loopback():
    hits = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            hits.append(self.path)
            if self.path.startswith("http://external.test"):
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/done")
                self.end_headers()
            else:
                self.send_response(200); self.end_headers(); self.wfile.write(b"done")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        p = NetworkPolicy(http_proxy=f"http://127.0.0.1:{server.server_port}")
        with HttpDownloadAdapter(p).open("http://external.test/item", timeout=2) as response:
            assert response.read() == b"done"
        assert hits == ["http://external.test/item", "/done"]
    finally:
        server.shutdown(); server.server_close(); thread.join()


def _git(*args):
    return subprocess.check_output(["git", *map(str,args)], text=True, encoding="utf-8").strip()


def test_real_git_pinned_old_commit_shallow_and_recovery(tmp_path):
    origin = tmp_path / "origin"; origin.mkdir()
    _git("init", origin)
    _git("-C", origin, "config", "user.name", "Test")
    _git("-C", origin, "config", "user.email", "test@example.invalid")
    (origin / "train.py").write_text("first")
    _git("-C", origin, "add", "."); _git("-C", origin, "commit", "-m", "first")
    first = _git("-C", origin, "rev-parse", "HEAD")
    (origin / "train.py").write_text("second")
    _git("-C", origin, "commit", "-am", "second")
    target = tmp_path / "cache"
    # Simulate a failed initial fetch: init succeeded, no checkout exists.
    _git("init", target)
    events = []
    adapter = GitDownloadAdapter(NetworkPolicy(mode="direct"), events.append)
    adapter.acquire(target, origin.as_uri(), first, lambda p: (p / "train.py").is_file())
    assert _git("-C", target, "rev-parse", "HEAD") == first
    assert _git("-C", target, "rev-list", "--count", "HEAD") == "1"
    assert (target / "train.py").read_text() == "first"
    (target / "keep.txt").write_text("user data")
    with pytest.raises(GitDownloadError, match="本地修改"):
        adapter.acquire(target, origin.as_uri(), first, lambda p: True)
    assert (target / "keep.txt").read_text() == "user data"


def test_git_refuses_non_git_directory(tmp_path):
    (tmp_path / "keep.txt").write_text("keep")
    with pytest.raises(GitDownloadError, match="不是 Git"):
        GitDownloadAdapter().acquire(tmp_path, "https://unused.invalid/repo", None, lambda p: True)
    assert (tmp_path / "keep.txt").exists()


def test_git_transient_retry_and_proxy_config(monkeypatch):
    import io
    import mikazuki.networking.git as mod
    invocations = []
    outputs = [(1, 'Connection reset\n'), (0, 'ok\n')]
    class Process:
        def __init__(self, command, **kwargs):
            invocations.append(kwargs)
            self.code, text = outputs.pop(0)
            self.stdout = io.StringIO(text)
        def wait(self, **kwargs): return self.code
        def poll(self): return self.code
    monkeypatch.setattr(mod.subprocess, "Popen", Process)
    monkeypatch.setattr(mod.time, "sleep", lambda delay: None)
    p = NetworkPolicy(https_proxy="http://u:secret@localhost:80")
    lines = []
    adapter = GitDownloadAdapter(p, lines.append)
    assert adapter.run(["ls-remote", "https://git.test/repo"], url="https://git.test/repo", retry=True) == "ok"
    assert len(invocations) == 2
    assert invocations[0]["env"]["HTTPS_PROXY"] == p.https_proxy
    assert "secret" not in str(lines)
    outputs[:] = [(1, 'fatal: repository not found\n')]
    with pytest.raises(GitDownloadError):
        adapter.run(["fetch"], retry=True)
    assert not outputs


def test_task_policy_is_stable_until_next_task(tmp_path, monkeypatch):
    from mikazuki.networking.policy import task_policy
    path = tmp_path / 'policy.json'
    monkeypatch.setenv('NEXT_TRAINER_NETWORK_CONFIG', str(path))
    path.write_text('{"mode":"direct"}')
    with task_policy() as current:
        path.write_text('{"mode":"manual", "https_proxy":"http://localhost:7890"}')
        assert resolve_policy() is current
        assert resolve_policy().mode == 'direct'
    assert resolve_policy().mode == 'manual'


def test_startup_injection_does_not_become_an_environment_override(monkeypatch, tmp_path):
    import mikazuki.networking.policy as mod
    monkeypatch.setattr(mod, '_startup_proxy_env', None)
    for key in list(mod.os.environ):
        if key.lower() in {'http_proxy','https_proxy','all_proxy','no_proxy'}:
            monkeypatch.delenv(key)
    # Register keys with monkeypatch so injected values are cleaned after test.
    monkeypatch.setenv('HTTP_PROXY', '')
    monkeypatch.setenv('HTTPS_PROXY', '')
    monkeypatch.setenv('NO_PROXY', '')
    path = tmp_path / 'policy.json'
    monkeypatch.setenv('NEXT_TRAINER_NETWORK_CONFIG', str(path))
    path.write_text('{"mode":"manual", "https_proxy":"http://localhost:7890"}')
    mod.initialize_sdk_environment()
    assert mod.os.environ['HTTPS_PROXY'] == 'http://localhost:7890'
    path.write_text('{"mode":"auto"}')
    assert mod.resolve_policy(system={}).https_proxy is None


def test_model_worker_runs_without_mutating_host_environment(tmp_path, monkeypatch):
    from mikazuki.networking.process import download_models
    import os
    path = tmp_path / 'policy.json'
    path.write_text('{"mode":"direct"}')
    monkeypatch.setenv('NEXT_TRAINER_NETWORK_CONFIG', str(path))
    monkeypatch.setenv('HTTPS_PROXY', 'http://localhost:1')
    messages = []
    # Empty selection exercises the actual SDK worker protocol without downloading models.
    download_models('anima-lora', [], 'huggingface', tmp_path, messages.append)
    assert os.environ['HTTPS_PROXY'] == 'http://localhost:1'
    assert 'direct' in messages[0]


def test_source_diagnostics_do_not_serialize_credentials():
    from mikazuki.download_sources import DownloadSources
    sources = DownloadSources(pip_index_url='https://user:secret@index.test/simple?token=secret')
    assert 'secret' not in str(sources.as_dict())
    # The actual installer still gets the original URL.
    assert 'secret' in sources.pip_index_url


def test_portable_bridge_proxy_is_not_mistaken_for_operator_env(monkeypatch):
    import mikazuki.networking.policy as mod
    monkeypatch.setattr(mod, '_startup_proxy_env', None)
    monkeypatch.setenv(mod.ORIGINAL_PROXY_ENV, '{"NO_PROXY":"localhost"}')
    monkeypatch.setenv('HTTPS_PROXY', 'http://old-manual:7890')
    policy = mod.resolve_policy(saved={'mode': 'auto'}, system={'https': 'system:7891'})
    assert policy.https_proxy == 'http://system:7891'

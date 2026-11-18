"""Forward compatibility: pre-standalone releases trained in the main
environment (portable python_embeded / GUI interpreter). When the standalone
extensions/kohya env is absent or broken, a passing main-env audit must report
ready instead of forcing a reinstall.
"""
import sys
from pathlib import Path

import pytest

from mikazuki.engines.kohya.settings import Runtime, main_env_python_candidates
from mikazuki.engines.kohya import extension_state
from mikazuki.engines.kohya.extension_state import read_status, write_state, fingerprint


@pytest.fixture(autouse=True)
def clear_audit_cache():
    extension_state._MAIN_ENV_AUDIT_CACHE.clear()
    yield
    extension_state._MAIN_ENV_AUDIT_CACHE.clear()


@pytest.fixture
def main_python(tmp_path):
    python = tmp_path / "python_embeded" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_text("fake", encoding="utf-8")
    return python


def patch_main_env(monkeypatch, python, audit):
    monkeypatch.setattr(extension_state, "main_env_python_candidates", lambda root: [python])
    monkeypatch.setattr(extension_state, "audit_python", lambda p, **kw: audit)


def test_candidates_include_portable_embedded_and_interpreter(tmp_path):
    project_root = tmp_path / "Next-Trainer"
    project_root.mkdir()
    embedded = tmp_path / "python_embeded" / "python.exe"
    embedded.parent.mkdir()
    embedded.write_text("fake", encoding="utf-8")

    candidates = main_env_python_candidates(project_root)

    assert embedded in candidates
    assert Path(sys.executable) in candidates
    assert len(candidates) == len({str(p.resolve()) for p in candidates})


def test_candidates_skip_missing_portable_layout(tmp_path):
    project_root = tmp_path / "Next-Trainer"
    project_root.mkdir()

    assert main_env_python_candidates(project_root) == [Path(sys.executable)]


def test_fallback_ready_when_standalone_missing(tmp_path, monkeypatch, main_python):
    patch_main_env(monkeypatch, main_python, {"ok": True, "torch": "2.7.0", "gpu": True})

    status = read_status(Runtime(tmp_path / "Next-Trainer"))

    assert status["state"] == "ready"
    assert status["facts"]["mode"] == "main_env"
    assert status["facts"]["standalone_state"] == "not_installed"
    assert status["runtime"]["python"] == str(main_python)


def test_fallback_failure_keeps_not_installed(tmp_path, monkeypatch, main_python):
    patch_main_env(monkeypatch, main_python, {"ok": False, "errors": ["no torch"]})

    status = read_status(Runtime(tmp_path / "Next-Trainer"))

    assert status["state"] == "not_installed"
    assert status["facts"]["main_env_rejected"]["python"] == str(main_python)
    assert status["facts"]["main_env_rejected"]["errors"] == ["no torch"]


def test_standalone_ready_wins_without_main_env_audit(tmp_path, monkeypatch, main_python):
    runtime = Runtime(tmp_path / "Next-Trainer")
    runtime.python.parent.mkdir(parents=True)
    runtime.python.write_text("fake", encoding="utf-8")
    write_state(runtime, "ready", {"fingerprint": fingerprint(runtime)})

    def forbidden_audit(python):
        raise AssertionError("main env audit must not run when standalone is ready")

    monkeypatch.setattr(extension_state, "main_env_python_candidates", lambda root: [main_python])
    monkeypatch.setattr(extension_state, "audit_python", forbidden_audit)

    status = read_status(runtime)

    assert status["state"] == "ready"
    assert status["facts"]["mode"] == "standalone"
    assert status["runtime"]["python"] == str(runtime.python)


def test_broken_standalone_falls_back_to_main_env(tmp_path, monkeypatch, main_python):
    runtime = Runtime(tmp_path / "Next-Trainer")
    write_state(runtime, "ready", {"fingerprint": "stale"})
    patch_main_env(monkeypatch, main_python, {"ok": True, "gpu": True})

    status = read_status(runtime)

    assert status["state"] == "ready"
    assert status["facts"]["mode"] == "main_env"
    assert status["facts"]["standalone_state"] == "broken"


def test_interrupted_install_falls_back(tmp_path, monkeypatch, main_python):
    runtime = Runtime(tmp_path / "Next-Trainer")
    write_state(runtime, "installing", {"task_id": "kohya-install-missing"})
    patch_main_env(monkeypatch, main_python, {"ok": True, "gpu": True})

    status = read_status(runtime)

    assert status["state"] == "ready"
    assert status["facts"]["mode"] == "main_env"
    assert status["facts"]["standalone_state"] == "broken"


def test_main_env_audit_results_are_cached(tmp_path, monkeypatch, main_python):
    calls = []

    def audit(python, **kw):
        calls.append(str(python))
        return {"ok": True, "gpu": True}

    monkeypatch.setattr(extension_state, "main_env_python_candidates", lambda root: [main_python])
    monkeypatch.setattr(extension_state, "audit_python", audit)
    runtime = Runtime(tmp_path / "Next-Trainer")

    read_status(runtime)
    read_status(runtime)

    assert calls == [str(main_python)]


def test_main_env_audit_failure_cached_briefly(tmp_path, monkeypatch, main_python):
    calls = []

    def audit(python, **kw):
        calls.append(str(python))
        return {"ok": False, "errors": ["no torch"]}

    monkeypatch.setattr(extension_state, "main_env_python_candidates", lambda root: [main_python])
    monkeypatch.setattr(extension_state, "audit_python", audit)
    runtime = Runtime(tmp_path / "Next-Trainer")

    read_status(runtime)
    read_status(runtime)

    # One cache miss; each miss probes isolated first, then with user site.
    assert calls == [str(main_python), str(main_python)]


def test_main_env_audit_retries_with_user_site_only_on_failure(monkeypatch, main_python):
    calls = []

    def audit(python, allow_user_site=False):
        calls.append(allow_user_site)
        return {"ok": True, "gpu": True} if allow_user_site else {"ok": False, "errors": ["no torch"]}

    monkeypatch.setattr(extension_state, "audit_python", audit)
    result = extension_state.audit_main_env_python(main_python)
    assert result["ok"] is True
    assert calls == [False, True]

    calls.clear()

    def audit_ok(python, allow_user_site=False):
        calls.append(allow_user_site)
        return {"ok": True, "gpu": True}

    monkeypatch.setattr(extension_state, "audit_python", audit_ok)
    assert extension_state.audit_main_env_python(main_python)["ok"] is True
    assert calls == [False]


def test_remove_extension_never_touches_main_env(tmp_path, main_python):
    runtime = Runtime(tmp_path / "Next-Trainer")
    runtime.root.mkdir(parents=True)
    write_state(runtime, "ready", {"fingerprint": "x"})

    from mikazuki.engines.kohya.installer import remove_extension

    remove_extension(runtime)

    assert not runtime.root.exists()
    assert main_python.is_file()


def _make_dist_info(runtime, name, version):
    meta = runtime.root / ".venv" / "lib" / "python3.10" / "site-packages" / f"{name}-{version}.dist-info" / "METADATA"
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n", encoding="utf-8")


def _make_ready_standalone(runtime):
    runtime.python.parent.mkdir(parents=True, exist_ok=True)
    runtime.python.write_text("fake", encoding="utf-8")
    write_state(runtime, "ready", {"fingerprint": "whatever"})


def test_standalone_ready_with_drift_reports_update_available(tmp_path):
    runtime = Runtime(tmp_path)
    _make_ready_standalone(runtime)
    _make_dist_info(runtime, "transformers", "4.51.3")

    status = read_status(runtime)

    assert status["state"] == "ready"
    assert status["facts"]["mode"] == "standalone"
    assert status["facts"]["update_available"] is True
    drift = {d["name"]: d for d in status["facts"]["drift"]}
    assert drift["transformers"]["installed"] == "4.51.3"
    assert drift["transformers"]["spec"] == "==5.17.0"


def test_standalone_ready_without_drift_is_clean(tmp_path, monkeypatch):
    runtime = Runtime(tmp_path)
    _make_ready_standalone(runtime)
    monkeypatch.setattr(extension_state, "compute_drift", lambda versions: [])

    status = read_status(runtime)

    assert status["state"] == "ready"
    assert status["facts"]["update_available"] is False
    assert "drift" not in status["facts"]


def test_main_env_ready_reports_drift_from_audit_versions(tmp_path, monkeypatch, main_python):
    patch_main_env(monkeypatch, main_python, {"ok": True, "gpu": True, "versions": {"transformers": "4.51.3", "torch": "2.13.0+cu130"}})

    status = read_status(Runtime(tmp_path / "Next-Trainer"))

    assert status["state"] == "ready"
    assert status["facts"]["mode"] == "main_env"
    assert status["facts"]["update_available"] is True
    drift = {d["name"]: d for d in status["facts"]["drift"]}
    assert drift["transformers"]["installed"] == "4.51.3"


def test_main_env_upgrade_marker_drives_installing_state(tmp_path, monkeypatch, main_python):
    from mikazuki.tasks import tm, TaskStatus
    from types import SimpleNamespace

    patch_main_env(monkeypatch, main_python, {"ok": True, "gpu": True, "versions": {}})
    runtime = Runtime(tmp_path / "Next-Trainer")
    task_id = "kohya-install-upgrade-demo"
    tm.tasks[task_id] = SimpleNamespace(status=TaskStatus.RUNNING)
    try:
        extension_state.note_main_env_upgrade(main_python, task_id)
        status = read_status(runtime)
        assert status["state"] == "installing"
        assert status["facts"]["task_id"] == task_id

        tm.tasks[task_id].status = TaskStatus.FINISHED
        status = read_status(runtime)
        assert status["state"] == "ready"
        assert status["facts"]["mode"] == "main_env"
    finally:
        tm.tasks.pop(task_id, None)
        extension_state._ACTIVE_MAIN_ENV_UPGRADE = None


def _patch_route(monkeypatch, status):
    from mikazuki.engines.kohya import routes

    monkeypatch.setattr(routes, "read_status", lambda rt: status)
    return routes


def test_upgrade_route_rejects_when_not_ready(monkeypatch):
    routes = _patch_route(monkeypatch, {"state": "not_installed", "facts": {}})

    import asyncio
    response = asyncio.run(routes.upgrade({}))

    assert response.status == "fail"


def test_upgrade_route_short_circuits_when_no_drift(monkeypatch):
    routes = _patch_route(monkeypatch, {"state": "ready", "facts": {"mode": "standalone", "update_available": False}})

    import asyncio
    response = asyncio.run(routes.upgrade({}))

    assert response.status == "success"
    assert response.data["already_up_to_date"] is True


def test_upgrade_route_dispatches_by_mode(monkeypatch):
    calls = []

    async def fake_main_env(rt, python, sources, drift):
        calls.append(("main_env", python))
        return {"task_id": "t1"}

    async def fake_standalone(rt, sources, drift):
        calls.append(("standalone",))
        return {"task_id": "t2"}

    import asyncio
    drift = [{"name": "transformers", "spec": "==5.17.0", "installed": "4.51.3"}]

    routes = _patch_route(monkeypatch, {"state": "ready", "facts": {"mode": "main_env", "drift": drift}, "runtime": {"python": "/main/python"}})
    monkeypatch.setattr(routes, "start_main_env_upgrade", lambda rt, python, sources, d: calls.append(("main_env", python)) or {"task_id": "t1"})
    monkeypatch.setattr(routes, "start_upgrade", lambda rt, sources, d: calls.append(("standalone",)) or {"task_id": "t2"})
    response = asyncio.run(routes.upgrade({}))
    assert response.status == "success"
    assert calls == [("main_env", "/main/python")]

    calls.clear()
    routes = _patch_route(monkeypatch, {"state": "ready", "facts": {"mode": "standalone", "drift": drift}, "runtime": {"python": "/standalone/python"}})
    monkeypatch.setattr(routes, "start_main_env_upgrade", lambda rt, python, sources, d: calls.append(("main_env", python)) or {"task_id": "t1"})
    monkeypatch.setattr(routes, "start_upgrade", lambda rt, sources, d: calls.append(("standalone",)) or {"task_id": "t2"})
    response = asyncio.run(routes.upgrade({}))
    assert response.status == "success"
    assert calls == [("standalone",)]

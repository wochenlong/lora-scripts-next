"""Synthetic lifecycle only: no real installers, dependency downloads, or GPU jobs."""
import asyncio
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from mikazuki.download_sources import DownloadSources
from mikazuki.engines.moss import environment, extension_state, install_worker, installer, manifest
from mikazuki.engines.moss.resource import environment_lock
from mikazuki.engines.moss.settings import REQUIRED_SOURCE_FILES, Runtime
from mikazuki.tasks import TaskStatus


@pytest.fixture
def rt(tmp_path, monkeypatch):
    monkeypatch.setattr(environment.sys, "platform", "linux")
    monkeypatch.setattr(environment.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(extension_state, "source_commit", lambda runtime: manifest.UPSTREAM["commit"])
    from mikazuki.engines.moss import source_integrity
    monkeypatch.setattr(source_integrity, "verify_source", lambda runtime: {"source_commit": manifest.UPSTREAM["commit"]})
    return Runtime(tmp_path)


def make_source(rt):
    (rt.source / ".git").mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_SOURCE_FILES:
        path = rt.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# fake MOSS fixture\n", encoding="utf-8")


def make_python(rt):
    rt.python.parent.mkdir(parents=True, exist_ok=True)
    rt.python.write_text("fake isolated executable", encoding="utf-8")
    rt.python_install_dir.mkdir(parents=True, exist_ok=True)
    (rt.root / ".venv/pyvenv.cfg").write_text("home = " + str(rt.python_install_dir))


def audit_facts(rt, **updates):
    return {
        "python_version": "3.13.13", "base_prefix": str(rt.python_install_dir / "cpython-3.13"),
        "prefix": str(rt.root / ".venv"), "versions": dict(environment.EXPECTED_VERSIONS),
        "cuda": "13.2", "cuda_available": True, "bf16_supported": True, **updates,
    }


class FakeCommands:
    """Mock command boundary including source fetch, Python, and dependency audit."""
    def __init__(self, rt, *, fail_install=False, probe_updates=None):
        self.rt = rt
        self.commands = []
        self.fail_install = fail_install
        self.probe_updates = probe_updates or {}

    def __call__(self, command, **kwargs):
        self.commands.append((command, kwargs))
        if command[:2] == ["git", "clone"]:
            make_source(self.rt)
        if command[:3] == ["uv", "python", "install"]:
            self.rt.python_install_dir.mkdir(parents=True, exist_ok=True)
        if command[:2] == ["uv", "venv"]:
            make_python(self.rt)
        if command[:3] == ["uv", "pip", "install"] and self.fail_install:
            self.fail_install = False
            raise subprocess.CalledProcessError(1, command, stderr="simulated download failure")
        if command[-2:] == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, manifest.UPSTREAM["commit"] + "\n", "")
        if "-c" in command:
            assert command[0] == str(self.rt.python)
            assert "from library.moss.requests import CacheRequest, TrainRequest" in command[-1]
            assert "from library.moss.train import run_train" in command[-1]
            assert "from library.moss.cache import run_cache" in command[-1]
            assert "from_pretrained(" not in command[-1]
            assert kwargs["env"]["HF_HUB_OFFLINE"] == "1"
            return subprocess.CompletedProcess(command, 0, json.dumps(audit_facts(self.rt, **self.probe_updates)), "")
        return subprocess.CompletedProcess(command, 0, "", "")


def run_fake_install(rt, commands, repair=False):
    return install_worker.execute_plan(
        rt, {"commands": installer.installation_plan(rt), "repair": repair}, "mock-install",
        runner=commands, audit_fn=lambda runtime: environment.audit_environment(runtime, runner=commands),
    )


def test_manifest_and_paths_are_moss_only(rt):
    from mikazuki.engines.manifest import load_manifest
    parsed = load_manifest(manifest)
    assert parsed.engine_id == "moss"
    assert parsed.train_types == {"moss-image-anima-lora": "moss-image"}
    assert parsed.capabilities["model_families"] == ["moss-image"]
    assert rt.root == rt.project_root / "extensions/moss"
    assert rt.python_install_dir == rt.root / ".python"
    assert "train.py" not in REQUIRED_SOURCE_FILES
    assert "scripts/moss/train.py" in REQUIRED_SOURCE_FILES


def test_plan_pins_source_and_isolates_python_and_dependencies(rt, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/gui/packages")
    monkeypatch.setenv("PYTHONHOME", "/gui/python")
    monkeypatch.setenv("VIRTUAL_ENV", "/gui/venv")
    sources = DownloadSources(pip_index_url="https://pip.example/simple", pytorch_index_url="https://torch.example/whl", github_url_prefix="https://git.example/")
    commands = installer.installation_plan(rt, sources)
    assert "moss_lora" in commands[0]
    assert commands[0][-2] == "https://git.example/" + manifest.UPSTREAM["github"]
    assert commands[1][-1] == manifest.UPSTREAM["commit"]
    assert ["uv", "python", "install", "3.13", "--install-dir", str(rt.python_install_dir)] in commands
    venv = next(command for command in commands if command[:2] == ["uv", "venv"])
    assert "--managed-python" in venv
    pip_commands = [command for command in commands if command[:3] == ["uv", "pip", "install"]]
    assert all(command[command.index("--python") + 1] == str(rt.python) for command in pip_commands)
    assert "https://torch.example/whl/cu132" in pip_commands[0]
    assert all("--no-deps" in command for command in pip_commands[1:])
    assert any(environment.ANIME_TOOLS_COMMIT in arg for arg in pip_commands[1])
    assert not any("flash-attn" in arg or "sam3" in arg or arg == "sync" for command in commands for arg in command)
    env = environment.install_env(rt, sources)
    assert env["UV_PYTHON_INSTALL_DIR"] == str(rt.python_install_dir)
    assert env["PYTHONNOUSERSITE"] == "1"
    assert not any(key in env for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"))
    assert not rt.root.exists()  # planning has no side effects


def test_windows_dependency_plan_and_unsupported_host(rt, monkeypatch):
    monkeypatch.setattr(environment.sys, "platform", "win32")
    commands = environment.install_commands(rt, DownloadSources())
    assert any("triton-windows==3.8.0.post29" in command for command in commands)
    assert str(rt.python).replace("\\", "/").endswith("Scripts/python.exe")
    monkeypatch.setattr(environment.sys, "platform", "darwin")
    with pytest.raises(ValueError, match="CUDA"):
        installer.installation_plan(rt)


def test_complete_fake_pipeline_reaches_ready(rt):
    commands = FakeCommands(rt)
    assert run_fake_install(rt, commands)["ok"]
    status = extension_state.read_status(rt)
    assert status["state"] == "ready"
    assert status["facts"]["task_id"] == "mock-install"
    assert status["facts"]["source_commit"] == manifest.UPSTREAM["commit"]
    assert status["facts"]["audit"]["facts"]["cuda_available"]
    assert status["runtime"]["environment_path"] == str(rt.root)
    assert all(kwargs["cwd"] in (rt.project_root, rt.source) for _, kwargs in commands.commands)


def test_failed_install_is_retryable_without_cloning_over_source(rt):
    failed = FakeCommands(rt, fail_install=True)
    with pytest.raises(subprocess.CalledProcessError):
        run_fake_install(rt, failed)
    assert extension_state.read_status(rt)["state"] == "broken"
    retried = FakeCommands(rt)
    assert run_fake_install(rt, retried)["ok"]
    assert retried.commands[0][0][-3:] == ["fetch", "origin", manifest.UPSTREAM["commit"]]
    assert extension_state.read_status(rt)["state"] == "ready"


def test_retry_recovers_incomplete_source_and_repair_preserves_user_files(rt):
    rt.source.mkdir(parents=True)
    (rt.source / "partial-clone").touch()
    outside = rt.project_root / "user-output.safetensors"
    outside.write_text("untouched")
    run_fake_install(rt, FakeCommands(rt))
    assert not (rt.source / "partial-clone").exists()
    (rt.source / "untracked.txt").touch()
    run_fake_install(rt, FakeCommands(rt), repair=True)
    assert not (rt.source / "untracked.txt").exists()
    assert outside.read_text() == "untouched"
    assert extension_state.read_status(rt)["state"] == "ready"


@pytest.mark.parametrize("updates,match", [
    ({"cuda_available": False}, "GPU"), ({"cuda": None}, "CUDA"),
    ({"bf16_supported": False}, "BF16"), ({"python_version": "3.12.9"}, "3.13"),
    ({"base_prefix": "/gui/python"}, "独立 Python"),
    ({"prefix": "/gui/venv"}, "venv"), ({"versions": {}}, "依赖版本"),
])
def test_audit_rejects_unusable_or_shared_runtime(rt, updates, match):
    make_source(rt)
    make_python(rt)
    result = environment.audit_environment(rt, runner=FakeCommands(rt, probe_updates=updates))
    assert not result["ok"]
    assert match in "; ".join(result["errors"])


def test_gpu_failure_never_publishes_ready(rt):
    with pytest.raises(RuntimeError, match="GPU"):
        run_fake_install(rt, FakeCommands(rt, probe_updates={"cuda_available": False}))
    status = extension_state.read_status(rt)
    assert status["state"] == "broken"
    assert status["facts"]["audit"]["ok"] is False


def test_audit_rejects_wrong_source_pin_before_python_execution(rt):
    make_source(rt)
    make_python(rt)
    calls = []
    def wrong_pin(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "f" * 40 if "rev-parse" in command else "", "")
    result = environment.audit_environment(rt, runner=wrong_pin)
    assert not result["ok"]
    assert "钉版" in result["errors"][0]
    assert not any("-c" in command for command in calls)


def test_missing_source_and_malformed_probe_fail_cleanly(rt):
    assert not environment.audit_environment(rt, runner=lambda *a, **k: pytest.fail("must not execute"))["ok"]
    make_source(rt)
    make_python(rt)
    base = FakeCommands(rt)
    def malformed(command, **kwargs):
        if "-c" in command:
            return subprocess.CompletedProcess(command, 0, "not json", "")
        return base(command, **kwargs)
    assert not environment.audit_environment(rt, runner=malformed)["ok"]


def test_content_drift_not_mtime_drift_invalidates_ready(rt, monkeypatch):
    import os
    run_fake_install(rt, FakeCommands(rt))
    code = rt.source / "library/moss/requests.py"
    os.utime(code, (1, 1))
    assert extension_state.read_status(rt)["state"] == "ready"
    original = code.read_text()
    code.write_text(original.replace("fake", "FAKE"))
    assert extension_state.read_status(rt)["state"] == "broken"
    code.write_text(original)
    monkeypatch.setattr(extension_state, "source_commit", lambda runtime: "0" * 40)
    assert extension_state.read_status(rt)["state"] == "broken"


def test_package_metadata_and_missing_entry_invalidate_ready(rt):
    run_fake_install(rt, FakeCommands(rt))
    metadata = rt.root / ".venv/lib/python3.13/site-packages/torch-2.dist-info/METADATA"
    metadata.parent.mkdir(parents=True)
    metadata.write_text("different torch")
    assert extension_state.read_status(rt)["state"] == "broken"
    metadata.unlink()
    (rt.source / "scripts/moss/cache.py").unlink()
    assert extension_state.read_status(rt)["state"] == "broken"


def test_missing_state_recovers_only_after_audit_and_corruption_is_broken(rt):
    assert extension_state.read_status(rt)["state"] == "not_installed"
    run_fake_install(rt, FakeCommands(rt))
    rt.state_file.unlink()
    called = []
    def audit(runtime):
        called.append(runtime)
        return environment.audit_environment(runtime, runner=FakeCommands(runtime))
    assert extension_state.read_status(rt, audit_fn=audit)["state"] == "ready"
    assert len(called) == 1
    assert extension_state.read_status(rt, audit_fn=audit)["state"] == "ready"
    assert len(called) == 1
    rt.state_file.write_text("{")
    assert extension_state.read_status(rt)["state"] == "broken"


def test_interrupted_install_and_disabled_feature(rt, monkeypatch):
    extension_state.write_state(rt, "installing", {"task_id": "absent-task"})
    assert extension_state.read_status(rt)["state"] == "broken"
    monkeypatch.setenv("LORA_ENABLE_MOSS", "0")
    assert extension_state.read_status(rt)["state"] == "disabled"
    with pytest.raises(ValueError):
        extension_state.check_runtime(rt)


@pytest.mark.parametrize("payload", [
    {"state": "unknown", "facts": {}},
    {"state": "ready", "facts": {"audit": "corrupt"}},
    {"state": "ready", "facts": []},
])
def test_invalid_state_shape_never_claims_ready(rt, payload):
    make_source(rt)
    make_python(rt)
    rt.state_file.write_text(json.dumps(payload))
    assert extension_state.read_status(rt)["state"] == "broken"


def test_check_runtime_rechecks_gpu_at_submission(rt, monkeypatch):
    run_fake_install(rt, FakeCommands(rt))
    monkeypatch.setattr(environment, "audit_environment", lambda runtime: {"ok": False, "errors": ["GPU disconnected"]})
    with pytest.raises(ValueError, match="GPU disconnected"):
        extension_state.check_runtime(rt)
    assert extension_state.read_status(rt)["state"] == "broken"


def test_lock_prevents_concurrent_worker_or_uninstall(rt):
    with environment_lock(rt.root):
        with pytest.raises(ValueError, match="正在使用中"):
            with environment_lock(rt.root):
                pass
        with pytest.raises(ValueError, match="正在使用中"):
            installer.remove_extension(rt)


def test_background_install_task_contract_without_launch(rt, monkeypatch):
    created = []
    task = SimpleNamespace(status=TaskStatus.CREATED, metadata={})
    task.execute = lambda: setattr(task, "status", TaskStatus.RUNNING)
    task.wait = lambda: None
    def create(command, env, **kwargs):
        created.append((command, env, kwargs))
        task.metadata = kwargs["metadata"]
        return task
    monkeypatch.setattr(installer, "tm", SimpleNamespace(tasks={}, create_task=create))
    result = installer.start_install(rt)
    command, env, metadata = created[0]
    assert command[0] != str(rt.python)  # GUI owns only the task supervisor
    assert command[1].replace("\\", "/").endswith("moss/install_worker.py")
    assert metadata["lane"] == "maintenance"
    assert metadata["metadata"]["backend"] == "moss"
    assert metadata["metadata"]["kind"] == "moss_install"
    assert result["task_id"].startswith("moss-install-")
    assert result["log_stream"].endswith(result["task_id"])
    assert result["progress_stream"].endswith(result["task_id"])
    assert json.loads(rt.state_file.read_text())["facts"]["task_id"] == result["task_id"]
    assert not rt.source.exists()


def test_active_tasks_block_mutation_but_training_can_check_maintenance_only(rt, monkeypatch):
    task = SimpleNamespace(status=TaskStatus.QUEUED, metadata={"backend": "moss", "kind": "train"})
    monkeypatch.setattr(installer, "tm", SimpleNamespace(tasks={"train": task}))
    with pytest.raises(ValueError, match="任务"):
        installer.start_install(rt)
    installer.assert_idle(maintenance_only=True)
    task.metadata["kind"] = "moss_install"
    with pytest.raises(ValueError, match="任务"):
        installer.assert_idle(maintenance_only=True)


def test_routes_dry_install_and_disabled_gate_do_not_spawn(rt, monkeypatch):
    # Keep this unit suite independent of the GUI's eager app package imports.
    import importlib.util
    import sys
    name = "mikazuki.app.models"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / "mikazuki/app/models.py")
        models = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, models)
        spec.loader.exec_module(models)
    from mikazuki.engines.moss import routes

    monkeypatch.setattr(routes, "runtime", lambda: rt)
    monkeypatch.setattr(routes, "start_install", lambda *a, **k: pytest.fail("must not spawn"))
    result = asyncio.run(routes.install({"dry_run": True}))
    assert result.status == "success" and result.data["plan"]
    assert not rt.root.exists()
    monkeypatch.setenv("LORA_ENABLE_MOSS", "0")
    assert asyncio.run(routes.install({"dry_run": False})).status == "fail"


def test_uninstall_preserves_external_data(rt, monkeypatch):
    monkeypatch.setattr(installer, "tm", SimpleNamespace(tasks={}))
    run_fake_install(rt, FakeCommands(rt))
    output = rt.project_root / "model.safetensors"
    output.write_text("user output")
    installer.remove_extension(rt)
    assert not rt.root.exists()
    assert output.read_text() == "user output"
    assert extension_state.read_status(rt)["state"] == "not_installed"

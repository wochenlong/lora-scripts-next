"""No downloads or training: exercise the real API up to the task boundary."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mikazuki.app import api
from mikazuki.download_sources import DownloadSources
from mikazuki.engines.kohaku_moss import (
    environment,
    extension_state,
    install_worker,
    installer,
    routes,
    run,
    settings,
)
from mikazuki.engines.kohaku_moss.manifest import UPSTREAM
from mikazuki.tasks import TaskStatus


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    rt = settings.Runtime(tmp_path)
    monkeypatch.setattr(run, "runtime", lambda: rt)
    monkeypatch.setattr(routes, "runtime", lambda: rt)
    for path in (rt.python, rt.kogine, rt.source / settings.TRAIN_SCRIPT):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# test fixture, never executed\n")
    extension_state.write_state(rt, "ready", {"test_fixture": True, "install_revision": settings.INSTALL_REVISION})
    return rt


def test_windows_install_reuses_next_isolated_environment(runtime, monkeypatch):
    monkeypatch.setattr(settings.sys, "platform", "win32")
    commands = installer.installation_plan(runtime, DownloadSources())
    assert runtime.python.relative_to(runtime.root) == Path(".venv/Scripts/python.exe")
    assert runtime.kogine.relative_to(runtime.root) == Path(".venv/Scripts/kogine.exe")
    assert commands[0][:2] == ["git", "clone"]
    assert commands[1][-1] == UPSTREAM["commit"]
    pip_commands = [c for c in commands if c[:3] == ["uv", "pip", "install"]]
    assert len(pip_commands) == 2
    assert all(c[c.index("--python") + 1] == str(runtime.python) for c in pip_commands)
    assert environment.LYCORIS_REQUIREMENT in pip_commands[-1]
    assert not any("setup.ps1" in part or "install.ps1" in part for c in commands for part in c)
    assert environment.install_env(runtime)["UV_PYTHON_INSTALL_DIR"] == str(runtime.python_install_dir)


def test_install_records_failure_and_retry_can_recover(runtime, monkeypatch):
    monkeypatch.setattr(install_worker.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("download failed")))
    with pytest.raises(RuntimeError, match="download failed"):
        install_worker.execute_plan(runtime, {"commands": [["uv", "--version"]]}, "install-test")
    assert extension_state.read_status(runtime)["state"] == "broken"
    monkeypatch.setattr(install_worker.subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(install_worker, "audit_environment", lambda rt: {"ok": True, "errors": [], "facts": {"synthetic": True}})
    install_worker.execute_plan(runtime, {"commands": [["uv", "--version"]]}, "retry-test")
    assert extension_state.read_status(runtime)["state"] == "ready"


def test_uninstall_preserves_other_engines_and_blocks_queued_work(runtime, monkeypatch):
    other = runtime.root.parent / "kohya" / "keep.txt"
    other.parent.mkdir(parents=True)
    other.write_text("keep")
    task = SimpleNamespace(metadata={"backend": "kohaku-moss"}, status=TaskStatus.QUEUED)
    monkeypatch.setattr(installer.tm, "tasks", {"queued": task})
    with pytest.raises(ValueError, match="尚未结束"):
        installer.remove_extension(runtime)
    assert runtime.root.exists()
    monkeypatch.setattr(installer.tm, "tasks", {})
    installer.remove_extension(runtime)
    assert not runtime.root.exists()
    assert other.read_text() == "keep"


def test_http_preflight_and_run_map_parameters_without_training(runtime, monkeypatch):
    monkeypatch.chdir(runtime.project_root)
    model = runtime.project_root / "model"
    for sub in ("transformer", "text_encoder", "vae"):
        (model / sub).mkdir(parents=True)
        (model / sub / "config.json").write_text("{}")
    dataset = runtime.project_root / "dataset"
    dataset.mkdir()
    (dataset / "image.png").write_bytes(b"synthetic image, no model loads")
    payload = {
        "model_train_type": "kohaku-moss-image-lora", "model_input_mode": "native_directory",
        "pretrained_model_name_or_path": str(model), "train_data_dir": str(dataset),
        "output_dir": str(runtime.project_root / "output"), "output_name": "ui-contract",
        "network_algorithm": "lokr", "network_dim": 24, "network_alpha": 12,
        "lokr_factor": 8, "lokr_full_matrix": True, "max_train_steps": 73,
        "lr_warmup_steps": 3, "learning_rate": 0.00023, "batching": "count", "batch_size": 2,
        "memory_profile": "low", "grad_acc": 3, "sample_every_n_steps": 10,
        "sample_prompts": "a red square\na blue square", "sample_width": 768,
        "sample_height": 1024, "gpu_ids": [0],
    }
    captured = []
    def create(command, env, metadata=None, cwd=None):
        from mikazuki.user_data import UserDataStore
        archive = UserDataStore().archive_task("never-executed", metadata)
        assert archive["engine_config"]["DIM"] == 24
        captured.append({"command": command, "env": env, "metadata": metadata, "cwd": cwd})
        return SimpleNamespace(task_id="never-executed", status=TaskStatus.CREATED)
    monkeypatch.setattr(run.tm, "create_task", create)
    monkeypatch.setattr(run.tm, "submit", lambda task: None)
    monkeypatch.setattr(run.tm, "tasks", {})
    app = FastAPI()
    app.include_router(api.router, prefix="/api")
    client = TestClient(app)
    preflight = client.post("/api/engines/kohaku-moss/preflight", json=payload).json()
    assert preflight["status"] == "success", preflight
    response = client.post("/api/run", json=payload).json()
    assert response["status"] == "success", response
    assert response["data"]["task_id"] == "never-executed"
    assert len(captured) == 1
    spec = captured[0]
    assert spec["command"][:6] == [str(runtime.python), "-E", "-s", "-u", "-X", "utf8"]
    assert spec["command"][8:10] == ["run", str(runtime.source / settings.TRAIN_SCRIPT)]
    values = {node.targets[0].id: ast.literal_eval(node.value) for node in ast.parse(Path(spec["metadata"]["engine_config_path"]).read_text()).body if isinstance(node, ast.Assign)}
    assert values["ALGO"] == "lokr"
    assert values["DIM"] == 24 and values["ALPHA"] == 12
    assert values["STEPS"] == 73 and values["SCHEDULE"]["warmup"] == 3
    assert values["LR"] == 0.00023 and values["GRAD_ACC"] == 3
    assert values["BATCH_SIZE"] == 2 and values["MEMORY_PROFILE"] == "low"
    assert values["SAMPLE_EVERY"] == 10
    assert values["SAMPLE_PROMPTS"] == ["a red square", "a blue square"]
    assert values["SAMPLE_SIZE"] == (768, 1024)
    assert spec["env"]["CUDA_VISIBLE_DEVICES"] == "0"


def test_literal_engine_config_archive_never_executes_python(tmp_path):
    from mikazuki.user_data import UserDataError, _configuration_snapshot
    config = tmp_path / "engine.py"
    config.write_text('"""Generated config."""\nDIM = 24\nCAPTION = {"keep": ()}\n')
    suffix, values, text = _configuration_snapshot(config)
    assert suffix == ".py" and values["DIM"] == 24
    assert ast.literal_eval(ast.parse(text).body[1].value) == {"keep": ()}
    for unsafe in ('import os', 'X = __import__("os").getcwd()', 'X = 1\nX = 2', 'X = object.name', 'X = [i for i in range(2)]'):
        config.write_text(unsafe)
        with pytest.raises(UserDataError):
            _configuration_snapshot(config)


def test_checkout_or_audit_failure_never_marks_ready(runtime, monkeypatch):
    (runtime.source / ".git").mkdir()
    calls = []
    def checkout_failure(command, **kwargs):
        calls.append(command)
        if "checkout" in command:
            raise RuntimeError("pinned revision unavailable")
    monkeypatch.setattr(install_worker.subprocess, "run", checkout_failure)
    plan = {"commands": installer.installation_plan(runtime)}
    with pytest.raises(RuntimeError, match="pinned revision"):
        install_worker.execute_plan(runtime, plan, "failed-checkout")
    assert extension_state.read_status(runtime)["state"] == "broken"
    assert calls[0][3:5] == ["fetch", "origin"]
    monkeypatch.setattr(install_worker.subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(install_worker, "audit_environment", lambda rt: {"ok": False, "errors": ["CUDA unavailable"]})
    with pytest.raises(RuntimeError, match="CUDA unavailable"):
        install_worker.execute_plan(runtime, plan, "failed-audit")
    assert extension_state.read_status(runtime)["state"] == "broken"


def test_metrics_and_previews_follow_pinned_upstream_layout(runtime, monkeypatch):
    import time

    import toml
    from PIL import Image

    from mikazuki.utils import task_insights
    now = time.time()
    output = runtime.project_root / 'output' / 'run'
    for step in (10, 20):
        path = output / 'samples' / f'step_{step:08d}' / '000.png'
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (8, 8)).save(path)
    rows = [{'time': now, 'step': 10, 'loss': 0.4, 'lr': 0.0001},
            {'time': now, 'step': 20, 'loss': 0.3, 'lr': 0.0001},
            {'time': now - 100, 'step': 1, 'loss': 99, 'lr': 0.0001}]
    (output / 'metrics.jsonl').write_text('\n'.join(json.dumps(row) for row in rows) + '\n{"step":')
    config = runtime.project_root / 'ui.toml'
    config.write_text(toml.dumps({'output_dir': str(output.parent), 'output_name': 'run',
                                 'sample_every_n_steps': 0, 'sample_prompts': 'a square'}))
    metadata = {'backend': 'kohaku-moss', 'config_path': str(config), 'output_dir': str(output),
                'logging_dir': str(output), 'output_name': 'run', 'total_steps': 100, 'started_at': now}
    monkeypatch.setattr(api.tm, 'tasks', {'metrics-test': SimpleNamespace(metadata=metadata)})
    monkeypatch.setattr(api.train_log_hub, 'tail', lambda *a: ['step \x1b[36m20\x1b[0m loss=0.3 lr=0.0001', 'retune_steps = 3'])
    app = FastAPI()
    app.include_router(api.router, prefix='/api')
    client = TestClient(app)
    metrics = client.get('/api/tasks/metrics-test/metrics').json()['data']
    assert metrics['progress'] == {'step': 20, 'total_steps': 100, 'percent': 20}
    assert metrics['tags']['loss/current'] == [{'step': 10, 'value': 0.4}, {'step': 20, 'value': 0.3}]
    previews = client.get('/api/tasks/metrics-test/previews').json()['data']
    assert previews['preview_enabled'] is False
    assert [item['step'] for item in previews['images']] == [10, 20]
    assert len({item['name'] for item in previews['images']}) == 2
    for item in previews['images']:
        assert client.get(item['url']).status_code == 200
    assert task_insights.resolve_preview_image(metadata, '../ui.toml') is None
    assert task_insights.resolve_task_dirs(metadata)['output_dir'] == output


def test_training_entry_holds_existing_environment_lock(runtime, monkeypatch):
    """Real child + real kogine, but its only payload is a stdin wait, never ML."""
    import subprocess
    import sys
    import time

    from mikazuki.engines.kohaku_moss import entry
    pytest.importorskip("kohakuengine")
    marker = runtime.project_root / 'waiting'
    script = runtime.source / settings.TRAIN_SCRIPT
    script.write_text(f'from pathlib import Path\nimport sys\ndef train():\n    Path({str(marker)!r}).touch()\n    sys.stdin.readline()\nif __name__ == "__main__":\n    train()\n')
    monkeypatch.setattr(installer.tm, 'tasks', {})
    child = subprocess.Popen([sys.executable, '-E', '-s', str(Path(entry.__file__)),
                              str(runtime.project_root), 'run', str(script)],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 10
        while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists(), 'harmless child did not reach its wait'
        with pytest.raises(ValueError, match='环境正在使用中'):
            installer.remove_extension(runtime)
        assert runtime.root.exists()
        stdout, stderr = child.communicate('\n', timeout=10)
        assert child.returncode == 0, stdout + stderr
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate()
    installer.remove_extension(runtime)
    assert not runtime.root.exists()


def test_installer_preserves_authenticated_sources_without_logging_credentials(runtime, monkeypatch, capsys):
    import threading
    secret = 'audit-placeholder-password'
    sources = DownloadSources(proxy_url=f'http://audit:{secret}@proxy.invalid:8080',
                              pip_index_url=f'https://audit:{secret}@index.invalid/simple')
    captured = {}
    def create(command, env, **kwargs):
        captured.update(plan=json.loads(Path(command[3]).read_text()))
        return SimpleNamespace(execute=lambda: None, wait=lambda: None)
    monkeypatch.setattr(installer.tm, 'tasks', {})
    monkeypatch.setattr(installer.tm, 'create_task', create)
    monkeypatch.setattr(threading.Thread, 'start', lambda self: None)
    installer.start_install(runtime, sources)
    assert captured['plan']['download_sources']['proxy_url'] == sources.proxy_url
    commands = []
    monkeypatch.setattr(install_worker.subprocess, 'run', lambda command, **kwargs: commands.append(kwargs['env']))
    monkeypatch.setattr(install_worker, 'audit_environment', lambda rt: {'ok': True})
    install_worker.execute_plan(runtime, captured['plan'], 'synthetic-install')
    assert all(env['HTTPS_PROXY'] == sources.proxy_url for env in commands)
    assert secret not in capsys.readouterr().out

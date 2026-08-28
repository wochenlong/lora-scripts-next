"""ai-toolkit pack routes: status/preflight/dry-run/install lifecycle + /api/run dispatch."""

import asyncio
import json

from pathlib import Path

from starlette.requests import Request

from mikazuki.app import api
from mikazuki.engines.ai_toolkit import routes


def make_request(payload: dict) -> Request:
    body = json.dumps(payload).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": "POST", "path": "/api/test", "headers": []}, receive)


def test_status_reports_not_installed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    response = asyncio.run(api.engine_status("ai-toolkit"))
    assert response.status == "success"
    assert response.data["state"] == "not_installed"
    assert response.data["feature_enabled"] is True
    assert set(response.data["train_types"]) == {"klein-4b-lora", "klein-9b-lora"}


def test_status_unknown_engine_404():
    try:
        asyncio.run(api.engine_status("no-such-engine"))
        raise AssertionError("expected HTTPException")
    except api.HTTPException as exc:
        assert exc.status_code == 404


def test_feature_flag_disables(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LORA_ENABLE_AI_TOOLKIT", "0")
    response = asyncio.run(api.engine_status("ai-toolkit"))
    assert response.data["feature_enabled"] is False
    response = asyncio.run(api.engine_preflight("ai-toolkit", make_request({})))
    assert response.status == "fail"
    assert "LORA_ENABLE_AI_TOOLKIT" in response.message


def test_dry_run_emits_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "train" / "klein"
    data_dir.mkdir(parents=True)
    (data_dir / "img1.png").write_bytes(b"")
    te_dir = tmp_path / "models" / "qwen3-8b"
    te_dir.mkdir(parents=True)
    payload = {
        "model_train_type": "klein-9b-lora",
        "pretrained_model_name_or_path": "black-forest-labs/FLUX.2-klein-base-9B",
        "text_encoder": str(te_dir),
        "train_data_dir": str(data_dir),
        "max_train_steps": 100,
    }
    response = asyncio.run(api.engine_dry_run("ai-toolkit", make_request(payload)))
    assert response.status == "success"
    assert response.data["variant"] == "klein-9b"
    yaml_path = Path(response.data["yaml_path"])
    assert yaml_path.is_file()
    text = yaml_path.read_text(encoding="utf-8")
    assert "flux2_klein_9b" in text
    assert response.data["config"]["config"]["process"][0]["model"]["arch"] == "flux2_klein_9b"


def test_dry_run_adapter_error_is_fail(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    response = asyncio.run(api.engine_dry_run("ai-toolkit", make_request({"model_train_type": "klein-4b-lora"})))
    assert response.status == "fail"


def test_install_dry_run_plan(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "vendor" / "ai-toolkit"
    (source / "toolkit").mkdir(parents=True)
    (source / "run.py").write_text("")
    # DIY vendor dirs must carry the pinned-commit marker to satisfy the pin
    (source / ".source_commit").write_text("5497a001cb8752c665f93907a0393fc612116fd5\n", encoding="utf-8")
    response = asyncio.run(api.engine_install("ai-toolkit", make_request({"dry_run": True})))
    assert response.status == "success"
    assert response.data["plan"]["dry_run"] is True
    assert response.data["plan"]["source_commit"] == "5497a001cb8752c665f93907a0393fc612116fd5"


def test_run_dispatch_reaches_pack_gate(tmp_path, monkeypatch):
    """klein train types dispatch to the ai-toolkit pack via /api/run's runner;
    the pack's ready gate rejects because the plugin is not installed."""
    from mikazuki.engines.runner import RunContext, dispatch_run

    monkeypatch.chdir(tmp_path)
    result = dispatch_run(
        "klein-4b-lora",
        {"train_data_dir": "/tmp/whatever"},
        RunContext(timestamp="t", autosave_dir=str(tmp_path), model_train_type="klein-4b-lora"),
    )
    assert result.status == "fail"
    assert "未就绪" in result.message


def test_run_dispatch_disabled_engine(tmp_path, monkeypatch):
    from mikazuki.engines.runner import RunContext, dispatch_run

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LORA_ENABLE_AI_TOOLKIT", "0")
    result = dispatch_run(
        "klein-9b-lora",
        {},
        RunContext(timestamp="t", autosave_dir=str(tmp_path), model_train_type="klein-9b-lora"),
    )
    assert result.status == "fail"
    assert "LORA_ENABLE_AI_TOOLKIT" in result.message


def test_handle_run_autosaves_ui_toml_for_reimport(tmp_path, monkeypatch):
    """config_path must point at a UI-dialect TOML (like kohya) so the
    /api/tasks/{id}/config re-import endpoint can parse it; the engine YAML
    stays traceable via engine_config_path."""
    from mikazuki.app.models import APIResponseSuccess
    from mikazuki.app.train_submit import toml
    from mikazuki.engines.ai_toolkit import run as aitk_run
    from mikazuki.engines.runner import RunContext

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(aitk_run, "ai_toolkit_feature_enabled", lambda: True)
    monkeypatch.setattr(aitk_run, "ai_toolkit_ready_gate", lambda: (True, None))

    class _Preflight:
        ok = True
        errors: list = []
        warnings: list = []

        def as_dict(self):
            return {}

    monkeypatch.setattr(aitk_run, "run_ai_toolkit_preflight", lambda *a, **k: _Preflight())

    captured = {}

    def _fake_launch(config_yaml, runtime, variant, gpu_ids, metadata=None, te_path=""):
        captured["metadata"] = metadata
        captured["config_yaml"] = config_yaml
        return APIResponseSuccess(data={"task_id": "t-1"})

    monkeypatch.setattr(aitk_run.process, "run_ai_toolkit_train", _fake_launch)

    data_dir = tmp_path / "train"
    data_dir.mkdir()
    (data_dir / "img.png").write_bytes(b"")
    te_dir = tmp_path / "te"
    te_dir.mkdir()
    for name in ("config.json", "tokenizer.json", "tokenizer_config.json"):
        (te_dir / name).write_text("{}", encoding="utf-8")
    (te_dir / "model.safetensors").write_bytes(b"")

    config = {
        "train_data_dir": str(data_dir),
        "pretrained_model_name_or_path": "black-forest-labs/FLUX.2-klein-base-4B",
        "text_encoder": str(te_dir),
        "max_train_steps": 100,
        "network_dim": 32,
    }
    ctx = RunContext(
        timestamp="20260828-120000",
        autosave_dir=str(tmp_path / "autosave"),
        model_train_type="klein-4b-lora",
        variant="klein-4b",
    )
    (tmp_path / "autosave").mkdir()
    result = aitk_run.handle_run(config, ctx)
    assert result.status == "success"

    metadata = captured["metadata"]
    ui_toml = Path(metadata["config_path"])
    assert ui_toml.suffix == ".toml" and ui_toml.is_file()
    reloaded = toml.loads(ui_toml.read_text(encoding="utf-8"))
    assert reloaded["network_dim"] == 32
    assert reloaded["max_train_steps"] == 100
    engine_yaml = Path(metadata["engine_config_path"])
    assert engine_yaml.suffix == ".yaml" and engine_yaml.is_file()
    assert str(engine_yaml) == captured["config_yaml"]


def test_task_train_type_for_ai_toolkit_backend():
    class _Task:
        metadata = {"backend": "ai-toolkit", "train_type": "klein-9b-lora"}

    assert api._task_train_type(_Task()) == "klein-9b-lora"

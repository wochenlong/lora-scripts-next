"""ai-toolkit pack routes: status/preflight/dry-run/install lifecycle + /api/run dispatch."""

import asyncio
import json
import struct

from pathlib import Path

from PIL import Image
from starlette.requests import Request

from mikazuki.app import api
from mikazuki.engines.ai_toolkit import routes


def _local_model(tmp_path: Path, variant="4b") -> dict:
    model = tmp_path / "models"
    te = model / "text_encoder"
    te.mkdir(parents=True, exist_ok=True)
    hidden_size = 2560 if variant == "4b" else 4096
    (te / "config.json").write_text(json.dumps({"hidden_size": hidden_size}), encoding="utf-8")
    for name in ("tokenizer.json", "tokenizer_config.json"):
        (te / name).write_text("{}", encoding="utf-8")
    header = json.dumps({"weight": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}}).encode()
    header += b" " * (-len(header) % 8)
    for path in (model / f"flux-2-klein-base-{variant}.safetensors",
                 model / "ae.safetensors", te / "model.safetensors"):
        path.write_bytes(struct.pack("<Q", len(header)) + header + struct.pack("<f", 0))
    return {"model_input_mode": "model_directory", "model_path": str(model), "text_encoder_path": str(te)}


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
    assert set(response.data["train_types"]) == {
        "klein-4b-lora", "klein-9b-lora", "ai-toolkit-flux-lora",
        "ai-toolkit-sdxl-lora", "ai-toolkit-qwen-image-21-lora",
        "ai-toolkit-krea2-lora", "ai-toolkit-anima-lora",
    }


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
    Image.new("RGB", (8, 8)).save(data_dir / "img1.png")
    payload = {
        "model_train_type": "klein-9b-lora",
        **_local_model(tmp_path, "9b"),
        "train_data_dir": str(data_dir),
        "max_train_steps": 100,
    }
    response = asyncio.run(api.engine_dry_run("ai-toolkit", make_request(payload)))
    assert response.status == "success", response.message
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
    (source / ".source_commit").write_text(routes.UPSTREAM["commit"] + "\n", encoding="utf-8")
    response = asyncio.run(api.engine_install("ai-toolkit", make_request({"dry_run": True})))
    assert response.status == "success", response.message
    assert response.data["plan"]["dry_run"] is True
    assert response.data["plan"]["source_commit"] == routes.UPSTREAM["commit"]


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
    Image.new("RGB", (8, 8)).save(data_dir / "img.png")

    config = {
        "train_data_dir": str(data_dir),
        **_local_model(tmp_path),
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
    assert result.status == "success", result.message

    metadata = captured["metadata"]
    ui_toml = Path(metadata["config_path"])
    assert ui_toml.suffix == ".toml" and ui_toml.is_file()
    reloaded = toml.loads(ui_toml.read_text(encoding="utf-8"))
    assert reloaded["network_dim"] == 32
    assert reloaded["max_train_steps"] == 100
    assert reloaded["model_input_mode"] == "model_directory"
    assert reloaded["model_path"] == config["model_path"]
    engine_yaml = Path(metadata["engine_config_path"])
    assert engine_yaml.suffix == ".yaml" and engine_yaml.is_file()
    assert str(engine_yaml) == captured["config_yaml"]


def test_task_train_type_for_ai_toolkit_backend():
    class _Task:
        metadata = {"backend": "ai-toolkit", "train_type": "klein-9b-lora"}

    assert api._task_train_type(_Task()) == "klein-9b-lora"


def test_handle_run_preserves_preview_settings(tmp_path, monkeypatch):
    """get_sample_prompts pops preview fields from the dict it gets; the adapter
    must still see the original sample_width/cfg/seed/steps/negative values."""
    import yaml

    from mikazuki.app.models import APIResponseSuccess
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
        captured["config_yaml"] = config_yaml
        return APIResponseSuccess(data={"task_id": "t-2"})

    monkeypatch.setattr(aitk_run.process, "run_ai_toolkit_train", _fake_launch)

    data_dir = tmp_path / "train"
    data_dir.mkdir()
    Image.new("RGB", (8, 8)).save(data_dir / "img.png")

    config = {
        "train_data_dir": str(data_dir),
        **_local_model(tmp_path),
        "max_train_steps": 100,
        "enable_preview": True,
        "positive_prompts": "a cat",
        "negative_prompts": "blurry",
        "sample_width": 768,
        "sample_height": 1152,
        "sample_cfg": 6.5,
        "sample_seed": 1234,
        "sample_steps": 33,
    }
    ctx = RunContext(
        timestamp="20260828-130000",
        autosave_dir=str(tmp_path / "autosave"),
        model_train_type="klein-4b-lora",
        variant="klein-4b",
    )
    (tmp_path / "autosave").mkdir()
    result = aitk_run.handle_run(config, ctx)
    assert result.status == "success", result.message

    process = yaml.safe_load(Path(captured["config_yaml"]).read_text(encoding="utf-8"))["config"]["process"][0]
    sample = process["sample"]
    assert sample["width"] == 768
    assert sample["height"] == 1152
    assert sample["guidance_scale"] == 6.5
    assert sample["seed"] == 1234
    assert sample["sample_steps"] == 33
    assert sample["neg"] == "blurry"
    assert sample["prompts"] == ["a cat"]
    assert sample["samples"] == [{
        "prompt": "a cat", "width": 768, "height": 1152, "guidance_scale": 6.5,
        "seed": 1234, "sample_steps": 33,
    }]

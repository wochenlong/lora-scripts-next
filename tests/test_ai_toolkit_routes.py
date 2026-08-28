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

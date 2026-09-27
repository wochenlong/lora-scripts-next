"""DiffSynth contract tests: no model weights or GPU training are used."""
import importlib.util
import json
import struct
from pathlib import Path

import pytest
from PIL import Image

from mikazuki.engines.diffsynth.adapter import adapt_config, dump_config
from mikazuki.engines.diffsynth.launcher import build_train_spec
from mikazuki.engines.diffsynth.settings import Runtime, TRAIN_SCRIPT
from mikazuki.engines.diffsynth.installer import installation_plan
from mikazuki.engines.diffsynth.manifest import UPSTREAM
from mikazuki.download_sources import DownloadSources


@pytest.fixture
def configured(tmp_path):
    rt = Runtime(tmp_path)
    model = tmp_path / "模型 with spaces"
    for folder, name in (("transformer", "diffusion_pytorch_model-00001.safetensors"), ("text_encoder", "model-00001.safetensors"), ("vae", "diffusion_pytorch_model.safetensors")):
        (model / folder).mkdir(parents=True)
        shapes = json.loads((Path(__file__).parent / "fixtures/diffsynth" / ({"transformer": "dit"}.get(folder, folder) + ".json")).read_text())
        headers, offset = {}, 0
        import math
        for key, shape in shapes.items():
            end = offset + math.prod(shape) * 2
            headers[key] = {"dtype": "BF16", "shape": shape, "data_offsets": [offset, end]}
            offset = end
        raw = json.dumps(headers).encode()
        with (model / folder / name).open("wb") as file:
            file.write(struct.pack("<Q", len(raw)) + raw)
            file.truncate(8 + len(raw) + offset)  # sparse fixture: headers only, no real model tensors

    (model / "processor").mkdir()
    for name in ("tokenizer.json", "tokenizer_config.json", "preprocessor_config.json", "chat_template.jinja", "video_preprocessor_config.json"):
        (model / "processor" / name).write_text("{}")
    dataset = tmp_path / "images" / "3_character"
    dataset.mkdir(parents=True)
    Image.new("RGBA", (32, 32), (255, 0, 0, 80)).save(dataset / "sample.png")
    (dataset / "sample.txt").write_text("中文提示词", encoding="utf-8")
    config = {"model_train_type": "qwen-image-21-lora", "diffsynth_model_dir": str(model), "train_data_dir": str(dataset.parent), "output_dir": str(tmp_path / "output"), "output_name": "test", "learning_rate": 0.0002, "num_epochs": 2, "lora_rank": 8}
    return rt, config


def test_data_conversion_preserves_alpha_repeats_and_unicode(configured):
    rt, config = configured
    adapted = adapt_config(config, rt)
    assert len(adapted.dataset) == 3
    assert adapted.dataset[0] == {"image": "3_character/sample.png", "prompt": "中文提示词"}
    image = Image.open(Path(config["train_data_dir"]) / adapted.dataset[0]["image"])
    assert image.mode == "RGBA" and image.getpixel((0, 0))[3] == 80
    assert adapted.arguments["dataset_repeat"] == 1
    assert adapted.arguments["dataset_num_workers"] == 0
    dump_config(adapted, rt.project_root / "autosave", "test")
    assert json.loads(Path(adapted.arguments["dataset_metadata_path"]).read_text()) == adapted.dataset


def test_official_arguments_and_process_isolation(configured, monkeypatch):
    rt, config = configured
    monkeypatch.setenv("PYTHONPATH", "/gui/packages")
    adapted = adapt_config(config, rt)
    path = dump_config(adapted, rt.project_root / "autosave", "test")
    spec = build_train_spec(rt, path, ["1"])
    assert spec.command[0] == str(rt.python)
    assert spec.command[spec.command.index("--config") + 1] == str(path)
    assert adapted.arguments["lora_rank"] == 8
    assert adapted.arguments["lora_target_modules"] == ""
    assert "PYTHONPATH" not in spec.env
    assert spec.env["CUDA_VISIBLE_DEVICES"] == "1"
    assert spec.env["HF_HUB_OFFLINE"] == "1"
    assert spec.cwd == rt.source


def test_missing_shard_fails_before_submission(configured):
    rt, config = configured
    index = Path(config["diffsynth_model_dir"]) / "transformer/diffusion_pytorch_model.safetensors.index.json"
    index.write_text(json.dumps({"weight_map": {"weight": "missing.safetensors"}}))
    with pytest.raises(ValueError, match="分片缺失"):
        adapt_config(config, rt)


def test_missing_caption_and_multiple_gpus_are_rejected(configured):
    rt, config = configured
    with pytest.raises(ValueError, match="单卡"):
        build_train_spec(rt, {}, ["0", "1"])
    (Path(config["train_data_dir"]) / "3_character/sample.txt").unlink()
    with pytest.raises(ValueError, match="标注"):
        adapt_config(config, rt)


def test_quantization_is_rejected(configured):
    rt, config = configured
    with pytest.raises(ValueError, match="量化"):
        adapt_config({**config, "diffsynth_quantization": "bitsandbytes_nf4"}, rt)


def test_install_uses_managed_python_complete_pin_and_mirrors(tmp_path):
    rt = Runtime(tmp_path)
    sources = DownloadSources(pip_index_url="https://pypi.example/simple", pytorch_index_url="https://torch.example/whl", github_url_prefix="https://git.example/")
    commands = installation_plan(rt, sources)
    assert commands[0][-2] == "https://git.example/" + UPSTREAM["github"]
    assert commands[1][-1] == UPSTREAM["commit"]
    assert ["uv", "python", "install", "3.12", "--install-dir", str(rt.python_install_dir)] in commands
    from mikazuki.engines.diffsynth.environment import install_env
    assert install_env(rt)["UV_PYTHON_INSTALL_DIR"] == str(rt.root / ".python")
    venv = next(c for c in commands if c[:2] == ["uv", "venv"])
    assert "--managed-python" in venv
    assert "--clear" in venv
    assert "https://torch.example/whl/cu128" in commands[-2]
    assert "https://pypi.example/simple" in commands[-1]
    assert "deepspeed" not in " ".join(commands[-1])


def test_import_export_roundtrip(configured):
    from mikazuki.utils.config_import import validate_config_import
    from mikazuki.utils.config_export import normalize_config_for_export
    _, config = configured
    exported, warnings = normalize_config_for_export(config, page_train_type="qwen-image-21-lora")
    result = validate_config_import("qwen-image-21-lora", exported)
    assert result["result"] == "ok", result
    assert result["config"]["lora_rank"] == 8


def test_api_run_routes_parameters_into_task_without_training(configured, monkeypatch):
    from fastapi.testclient import TestClient
    from mikazuki.app.application import app
    from mikazuki.engines.diffsynth import run
    from mikazuki.engines.diffsynth import preflight
    from mikazuki.engines.diffsynth.extension_state import write_state, fingerprint
    rt, config = configured
    monkeypatch.chdir(rt.project_root)
    rt.python.parent.mkdir(parents=True)
    rt.python.touch()
    (rt.source / TRAIN_SCRIPT).parent.mkdir(parents=True)
    (rt.source / TRAIN_SCRIPT).touch()
    write_state(rt, "ready", {"audit": {"ok": True}, "fingerprint": fingerprint(rt)})
    monkeypatch.setattr(preflight, "audit_environment", lambda runtime: {"ok": True, "errors": []})
    submitted = []
    monkeypatch.setattr(run.tm, "submit", submitted.append)
    client = TestClient(app)
    response = client.post("/api/run", json=config).json()
    assert response["status"] == "success", response
    assert len(submitted) == 1
    task = submitted[0]
    try:
        assert not hasattr(task, "process")
        assert task.command[0] == str(rt.python)
        arguments = json.loads(Path(task.metadata["engine_config_path"]).read_text())["arguments"]
        assert arguments["learning_rate"] == 0.0002
        assert arguments["num_epochs"] == 2
        assert arguments["lora_rank"] == 8
        assert response["data"]["metadata"]["backend"] == "diffsynth"
        assert Path(task.metadata["config_path"]).is_file()
    finally:
        run.tm.tasks.pop(task.task_id)


def test_not_installed_cannot_start(configured, monkeypatch):
    from fastapi.testclient import TestClient
    from mikazuki.app.application import app
    rt, config = configured
    monkeypatch.chdir(rt.project_root)
    response = TestClient(app).post("/api/run", json=config).json()
    assert response["status"] == "fail"
    assert "未就绪" in response["message"]


def test_loss_and_global_progress_use_upstream_log_formats(tmp_path):
    import time
    from tensorboard.summary.writer.event_file_writer import EventFileWriter
    from tensorboard.compat.proto.event_pb2 import Event
    from tensorboard.compat.proto.summary_pb2 import Summary
    from mikazuki.utils.task_insights import read_loss_scalars
    from mikazuki.engines.diffsynth.progress import read_progress
    log_dir = tmp_path / "tensorboard_log"
    writer = EventFileWriter(str(log_dir))
    writer.add_event(Event(wall_time=time.time(), step=3, summary=Summary(value=[Summary.Value(tag="loss", simple_value=0.25)])))
    writer.close()
    (tmp_path / "loss.csv").write_text("step,key,value\n1,loss,0.5\n3,loss,0.25\n")
    metadata = {"backend": "diffsynth", "output_dir": str(tmp_path), "logging_dir": str(log_dir), "output_name": "test", "total_steps": 12}
    assert read_loss_scalars(metadata)["loss"] == [{"step": 3, "value": 0.25}]
    assert read_progress([], {"backend": "diffsynth", "kind": "diffsynth_install"}) == {}
    assert read_progress(["100%|download|"], metadata) == {"step": 3, "total_steps": 12, "percent": 25, "loss": 0.25}

from pathlib import Path

from mikazuki.download_sources import DownloadSources
from mikazuki.engines.kohaku_moss.adapter import adapt_config, dump_config
from mikazuki.engines.kohaku_moss.environment import install_commands
from mikazuki.engines.kohaku_moss.manifest import ENGINE_ID, TRAIN_TYPES, UPSTREAM
from mikazuki.engines.kohaku_moss.settings import Runtime


def test_manifest_is_pinned_and_moss_only():
    assert ENGINE_ID == "kohaku-moss"
    assert TRAIN_TYPES == {"kohaku-moss-image-lora": "moss-image"}
    assert len(UPSTREAM["commit"]) == 40


def test_install_plan_uses_isolated_python_and_explicit_lycoris(tmp_path):
    runtime = Runtime(tmp_path)
    commands = install_commands(runtime, DownloadSources())
    flattened = " ".join(part for command in commands for part in command)
    assert "3.12" in flattened
    assert "lycoris-lora>=4.1.2" in flattened
    assert str(runtime.python) in flattened


def test_adapter_writes_native_kogine_python_config(tmp_path):
    runtime = Runtime(tmp_path)
    config = {
        "model_train_type": "kohaku-moss-image-lora",
        "pretrained_model_name_or_path": "models/MOSS-Image-Base",
        "train_data_dir": "train/moss",
        "output_dir": "output",
        "output_name": "dragon-test",
        "max_train_steps": 20,
        "network_algorithm": "lokr",
        "network_dim": 16,
        "memory_profile": "minimal",
    }
    adapted = adapt_config(config, runtime)
    assert adapted.values["ALGO"] == "lokr"
    assert adapted.values["STEPS"] == 20
    path = dump_config(adapted, tmp_path / "autosave", "test")
    text = Path(path).read_text(encoding="utf-8")
    assert "MEMORY_PROFILE = 'minimal'" in text
    assert "EXPORT_FORMATS = ('comfy', 'lycoris')" in text

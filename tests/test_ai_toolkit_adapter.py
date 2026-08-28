"""ai-toolkit adapter: UI (kohya-dialect) -> toolkit YAML tree, Klein variants."""

from pathlib import Path

import pytest
import yaml

from mikazuki.engines.ai_toolkit.adapter import (
    AdapterError,
    adapt_config,
    dump_yaml,
)
from mikazuki.engines.ai_toolkit.settings import RuntimeConfig


def _runtime(tmp_path: Path) -> RuntimeConfig:
    return RuntimeConfig(
        toolkit_root=tmp_path / "toolkit",
        python=tmp_path / "toolkit" / ".venv" / "bin" / "python",
        lora_next_root=tmp_path,
        output_dir=tmp_path / "output" / "ai-toolkit",
        logging_dir=tmp_path / "logs" / "ai-toolkit",
        cache_dir=tmp_path / ".cache" / "ai-toolkit",
    )


def _source(tmp_path: Path, **overrides) -> dict:
    data = tmp_path / "train" / "klein"
    data.mkdir(parents=True, exist_ok=True)
    base = {
        "model_train_type": "klein-4b-lora",
        "pretrained_model_name_or_path": "black-forest-labs/FLUX.2-klein-base-4B",
        "train_data_dir": str(data),
        "max_train_steps": 2000,
        "learning_rate": "1e-4",
        "network_dim": 32,
        "network_alpha": 32,
        "train_batch_size": 1,
        "resolution": "1024,1024",
        "caption_extension": ".txt",
        "optimizer_type": "AdamW8bit",
        "save_every_n_steps": 250,
    }
    base.update(overrides)
    return base


def _process(adapted):
    return adapted.config["config"]["process"][0]


def test_basic_mapping_4b(tmp_path):
    adapted = adapt_config(_source(tmp_path), _runtime(tmp_path), "run-1", "klein-4b")
    process = _process(adapted)
    assert adapted.config["job"] == "extension"
    assert process["type"] == "sd_trainer"
    assert process["model"]["arch"] == "flux2_klein_4b"
    assert process["model"]["name_or_path"] == "black-forest-labs/FLUX.2-klein-base-4B"
    assert process["model"]["quantize"] is True
    assert process["model"]["low_vram"] is False
    assert process["network"] == {"type": "lora", "linear": 32, "linear_alpha": 32}
    assert process["train"]["steps"] == 2000
    assert process["train"]["lr"] == pytest.approx(1e-4)
    assert process["train"]["optimizer"] == "adamw8bit"
    assert process["train"]["noise_scheduler"] == "flowmatch"
    assert process["train"]["timestep_type"] == "weighted"
    assert process["train"]["dtype"] == "bf16"
    assert process["datasets"][0]["resolution"] == [1024]
    assert process["datasets"][0]["caption_ext"] == "txt"
    assert process["datasets"][0]["cache_latents_to_disk"] is True
    assert process["save"]["save_every"] == 250
    assert adapted.warnings == []


def test_variant_9b(tmp_path):
    adapted = adapt_config(
        _source(tmp_path, pretrained_model_name_or_path="black-forest-labs/FLUX.2-klein-base-9B"),
        _runtime(tmp_path),
        "run-1",
        "klein-9b",
    )
    assert _process(adapted)["model"]["arch"] == "flux2_klein_9b"


def test_unknown_variant_rejected(tmp_path):
    with pytest.raises(AdapterError, match="未知 AI Toolkit 变体"):
        adapt_config(_source(tmp_path), _runtime(tmp_path), "run-1", "klein-2b")


def test_local_dit_file_maps_to_parent(tmp_path):
    dit = tmp_path / "models" / "flux-2-klein-base-4b.safetensors"
    dit.parent.mkdir(parents=True)
    dit.write_bytes(b"")
    adapted = adapt_config(
        _source(tmp_path, pretrained_model_name_or_path=str(dit)), _runtime(tmp_path), "run-1", "klein-4b"
    )
    assert _process(adapted)["model"]["name_or_path"] == str(dit.parent.resolve())
    assert adapted.warnings == []


def test_local_dit_file_wrong_name_warns(tmp_path):
    dit = tmp_path / "models" / "whatever.safetensors"
    dit.parent.mkdir(parents=True)
    dit.write_bytes(b"")
    adapted = adapt_config(
        _source(tmp_path, pretrained_model_name_or_path=str(dit)), _runtime(tmp_path), "run-1", "klein-4b"
    )
    assert any("不一致" in w for w in adapted.warnings)


def test_epochs_rejected_without_steps(tmp_path):
    with pytest.raises(AdapterError, match="只支持按步数"):
        adapt_config(
            _source(tmp_path, max_train_steps=None, max_train_epochs=16),
            _runtime(tmp_path),
            "run-1",
            "klein-4b",
        )


def test_epochs_warn_when_steps_present(tmp_path):
    adapted = adapt_config(
        _source(tmp_path, max_train_epochs=16), _runtime(tmp_path), "run-1", "klein-4b"
    )
    assert any("epoch" in w for w in adapted.warnings)
    assert _process(adapted)["train"]["steps"] == 2000


def test_missing_dataset_dir_rejected(tmp_path):
    with pytest.raises(AdapterError, match="数据集路径不存在"):
        adapt_config(
            _source(tmp_path, train_data_dir=str(tmp_path / "nope")),
            _runtime(tmp_path),
            "run-1",
            "klein-4b",
        )


def test_control_dirs_become_control_path(tmp_path):
    ctrl = tmp_path / "ctrl"
    ctrl.mkdir()
    adapted = adapt_config(
        _source(tmp_path, control_data_dirs=[str(ctrl)]), _runtime(tmp_path), "run-1", "klein-4b"
    )
    assert _process(adapted)["datasets"][0]["control_path"] == [str(ctrl.resolve())]


def test_control_dir_missing_rejected(tmp_path):
    with pytest.raises(AdapterError, match="参考图目录不存在"):
        adapt_config(
            _source(tmp_path, control_data_dirs=[str(tmp_path / "nope")]),
            _runtime(tmp_path),
            "run-1",
            "klein-4b",
        )


def test_sample_prompts_file_inline(tmp_path):
    prompts = tmp_path / "prompts.txt"
    prompts.write_text("a cat --n dog\n\na dog\n", encoding="utf-8")
    adapted = adapt_config(
        _source(tmp_path, sample_prompts=str(prompts), sample_every_n_steps=100, sample_cfg=4.0),
        _runtime(tmp_path),
        "run-1",
        "klein-4b",
    )
    sample = _process(adapted)["sample"]
    assert sample["prompts"] == ["a cat", "a dog"]
    assert sample["sampler"] == "flowmatch"
    assert sample["sample_every"] == 100
    assert sample["guidance_scale"] == pytest.approx(4.0)


def test_unknown_fields_warn(tmp_path):
    adapted = adapt_config(
        _source(tmp_path, some_random_field=1, _private=2), _runtime(tmp_path), "run-1", "klein-4b"
    )
    assert any("some_random_field" in w for w in adapted.warnings)
    assert not any("_private" in w for w in adapted.warnings)


def test_ema_opt_in(tmp_path):
    adapted = adapt_config(
        _source(tmp_path, use_ema=True, ema_decay=0.995), _runtime(tmp_path), "run-1", "klein-4b"
    )
    assert _process(adapted)["train"]["ema_config"] == {"use_ema": True, "ema_decay": pytest.approx(0.995)}
    adapted_off = adapt_config(_source(tmp_path), _runtime(tmp_path), "run-1", "klein-4b")
    assert "ema_config" not in _process(adapted_off)["train"]


def test_dump_yaml_roundtrip(tmp_path):
    adapted = adapt_config(_source(tmp_path), _runtime(tmp_path), "run-1", "klein-4b")
    text = dump_yaml(adapted.config)
    loaded = yaml.safe_load(text)
    assert loaded == adapted.config
    assert "klein-4b" not in text  # variant is not a toolkit key; arch carries it
    assert "flux2_klein_4b" in text

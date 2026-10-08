"""ai-toolkit adapter: UI (kohya-dialect) -> toolkit YAML tree, Klein variants."""

from pathlib import Path
import json
import struct

import pytest
import yaml
from PIL import Image

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
    Image.new("RGB", (8, 8)).save(data / "img.png")
    te = tmp_path / "models" / "qwen3-4b"
    te.mkdir(parents=True, exist_ok=True)
    (te / "config.json").write_text('{"hidden_size": 2560}', encoding="utf-8")
    for name in ("tokenizer.json", "tokenizer_config.json"):
        (te / name).write_text("{}", encoding="utf-8")
    for path in (te / "model.safetensors", te.parent / "flux-2-klein-base-4b.safetensors",
                 te.parent / "ae.safetensors"):
        _weights(path)
    base = {
        "model_train_type": "klein-4b-lora",
        "pretrained_model_name_or_path": str(te.parent),
        "text_encoder": str(te),
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


def _weights(path: Path):
    header = json.dumps({"weight": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}}).encode()
    header += b" " * (-len(header) % 8)
    path.write_bytes(struct.pack("<Q", len(header)) + header + struct.pack("<f", 0))


def _process(adapted):
    return adapted.config["config"]["process"][0]


def test_basic_mapping_4b(tmp_path):
    adapted = adapt_config(_source(tmp_path), _runtime(tmp_path), "run-1", "klein-4b")
    process = _process(adapted)
    assert adapted.config["job"] == "extension"
    assert process["type"] == "sd_trainer"
    assert process["model"]["arch"] == "flux2_klein_4b"
    assert Path(process["model"]["name_or_path"]) == tmp_path / "models" / "flux-2-klein-base-4b.safetensors"
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


def test_log_dir_defaults_to_runtime(tmp_path):
    adapted = adapt_config(_source(tmp_path), _runtime(tmp_path), "run-1", "klein-4b")
    process = _process(adapted)
    assert Path(process["log_dir"]) == tmp_path / "logs" / "ai-toolkit"
    assert process["logging"] == {"log_every": 20}


def test_log_dir_ui_override(tmp_path):
    adapted = adapt_config(_source(tmp_path, logging_dir="my-logs"), _runtime(tmp_path), "run-1", "klein-4b")
    process = _process(adapted)
    assert Path(process["log_dir"]) == (tmp_path / "my-logs").resolve()


def test_log_every_floored_for_short_runs(tmp_path):
    adapted = adapt_config(_source(tmp_path, max_train_steps=50), _runtime(tmp_path), "run-1", "klein-4b")
    process = _process(adapted)
    assert process["logging"] == {"log_every": 1}


def test_gradient_checkpointing_truthy_strings(tmp_path):
    adapted = adapt_config(_source(tmp_path), _runtime(tmp_path), "run-1", "klein-4b")
    assert _process(adapted)["train"]["gradient_checkpointing"] is True
    adapted = adapt_config(_source(tmp_path, gradient_checkpointing="false"), _runtime(tmp_path), "run-1", "klein-4b")
    assert _process(adapted)["train"]["gradient_checkpointing"] is False
    adapted = adapt_config(_source(tmp_path, gradient_checkpointing=0), _runtime(tmp_path), "run-1", "klein-4b")
    assert _process(adapted)["train"]["gradient_checkpointing"] is False


def test_sample_neg_from_negative_prompts(tmp_path):
    data = _source(tmp_path)
    data["preview_samples"] = [{"prompt": "a cat"}]
    data["negative_prompts"] = "blurry"
    adapted = adapt_config(data, _runtime(tmp_path), "run-1", "klein-4b")
    assert _process(adapted)["sample"]["neg"] == "blurry"


def test_max_grad_norm_mapped(tmp_path):
    adapted = adapt_config(_source(tmp_path), _runtime(tmp_path), "run-1", "klein-4b")
    assert _process(adapted)["train"]["max_grad_norm"] == pytest.approx(1.0)
    adapted = adapt_config(_source(tmp_path, max_grad_norm=0.5), _runtime(tmp_path), "run-1", "klein-4b")
    assert _process(adapted)["train"]["max_grad_norm"] == pytest.approx(0.5)


def test_control_dirs_blank_rows_rejected(tmp_path):
    ctrl = tmp_path / "control"
    ctrl.mkdir()
    with pytest.raises(AdapterError, match="control_data_dirs"):
        adapt_config(
            _source(tmp_path, control_data_dirs=[str(ctrl), "", "   "]),
            _runtime(tmp_path), "run-1", "klein-4b",
        )


def test_control_dirs_non_list_rejected(tmp_path):
    with pytest.raises(AdapterError, match="control_data_dirs"):
        adapt_config(_source(tmp_path, control_data_dirs=123), _runtime(tmp_path), "run-1", "klein-4b")


def test_variant_9b(tmp_path):
    source = _source(tmp_path)
    dit = tmp_path / "models" / "flux-2-klein-base-9b.safetensors"
    _weights(dit)
    (Path(source["text_encoder"]) / "config.json").write_text('{"hidden_size": 4096}', encoding="utf-8")
    adapted = adapt_config(
        source,
        _runtime(tmp_path),
        "run-1",
        "klein-9b",
    )
    assert _process(adapted)["model"]["arch"] == "flux2_klein_9b"
    assert Path(_process(adapted)["model"]["name_or_path"]) == dit


def test_unknown_variant_rejected(tmp_path):
    with pytest.raises(AdapterError, match="未知 AI Toolkit 变体"):
        adapt_config(_source(tmp_path), _runtime(tmp_path), "run-1", "klein-2b")


def test_te_path_side_channel(tmp_path):
    adapted = adapt_config(_source(tmp_path), _runtime(tmp_path), "run-1", "klein-4b")
    assert Path(adapted.te_path) == (tmp_path / "models" / "qwen3-4b").resolve()
    # The asset manifest retains the TE, but upstream model keys do not.
    assert "text_encoder" not in _process(adapted)["model"]
    assert adapted.config["meta"]["next_trainer"]["assets"]["text_encoder"] == adapted.te_path


def test_missing_te_rejected(tmp_path):
    source = _source(tmp_path)
    source["text_encoder"] = ""
    with pytest.raises(AdapterError, match="模型路径不能为空"):
        adapt_config(source, _runtime(tmp_path), "run-1", "klein-4b")


def test_te_dir_missing_preserved_for_preflight(tmp_path):
    source = _source(tmp_path, text_encoder=str(tmp_path / "nope"))
    adapted = adapt_config(source, _runtime(tmp_path), "run-1", "klein-4b")
    assert Path(adapted.te_path) == tmp_path / "nope"
    assert adapted.config["meta"]["next_trainer"]["assets"]["text_encoder"] == adapted.te_path


def test_local_dit_file_preserves_exact_path(tmp_path):
    dit = tmp_path / "models" / "flux-2-klein-base-4b.safetensors"
    dit.parent.mkdir(parents=True)
    _weights(dit)
    adapted = adapt_config(
        _source(tmp_path, pretrained_model_name_or_path=str(dit)), _runtime(tmp_path), "run-1", "klein-4b"
    )
    assert Path(_process(adapted)["model"]["name_or_path"]) == dit.resolve()
    assert adapted.warnings == []


def test_local_dit_file_custom_name_is_preserved(tmp_path):
    dit = tmp_path / "models" / "whatever.safetensors"
    dit.parent.mkdir(parents=True)
    _weights(dit)
    adapted = adapt_config(
        _source(tmp_path, pretrained_model_name_or_path=str(dit)), _runtime(tmp_path), "run-1", "klein-4b"
    )
    assert Path(_process(adapted)["model"]["name_or_path"]) == dit
    assert adapted.warnings == []


def test_epochs_rejected_without_steps(tmp_path):
    with pytest.raises(AdapterError, match="只支持按步数"):
        adapt_config(
            _source(tmp_path, max_train_steps=None, max_train_epochs=16),
            _runtime(tmp_path),
            "run-1",
            "klein-4b",
        )


def test_epochs_rejected_when_steps_present(tmp_path):
    with pytest.raises(AdapterError, match="max_train_epochs"):
        adapt_config(_source(tmp_path, max_train_epochs=16), _runtime(tmp_path), "run-1", "klein-4b")


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
    Image.new("RGB", (8, 8)).save(ctrl / "img.png")
    adapted = adapt_config(
        _source(tmp_path, control_data_dirs=[str(ctrl)]), _runtime(tmp_path), "run-1", "klein-4b"
    )
    assert [Path(p) for p in _process(adapted)["datasets"][0]["control_path"]] == [ctrl.resolve()]


def test_control_dir_missing_rejected(tmp_path):
    with pytest.raises(AdapterError, match="参考图目录必须存在"):
        adapt_config(
            _source(tmp_path, control_data_dirs=[str(tmp_path / "nope")]),
            _runtime(tmp_path),
            "run-1",
            "klein-4b",
        )


def test_sample_prompts_file_requires_explicit_conversion(tmp_path):
    prompts = tmp_path / "prompts.txt"
    prompts.write_text("a cat --n dog\n\na dog\n", encoding="utf-8")
    with pytest.raises(AdapterError, match="preview_samples"):
        adapt_config(_source(tmp_path, sample_prompts=str(prompts)), _runtime(tmp_path), "run-1", "klein-4b")
    adapted = adapt_config(
        _source(tmp_path, preview_samples=[{"prompt": "a cat"}, {"prompt": "a dog"}],
                sample_every_n_steps=100, sample_cfg=4.0),
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
    assert any("_private" in w for w in adapted.warnings)
    assert "some_random_field" not in dump_yaml(adapted.config)
    assert "_private" not in dump_yaml(adapted.config)


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
    assert "variant" not in _process(adapted)["model"]
    assert loaded["meta"]["next_trainer"]["assets"]["variant"] == "klein-4b"
    assert "flux2_klein_4b" in text

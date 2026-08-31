"""ai-toolkit adapter: UI (kohya-dialect) -> toolkit YAML tree, Klein variants."""

from pathlib import Path
import json

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
    te = tmp_path / "models" / "qwen3-4b"
    te.mkdir(parents=True, exist_ok=True)
    base = {
        "model_train_type": "klein-4b-lora",
        "pretrained_model_name_or_path": "black-forest-labs/FLUX.2-klein-base-4B",
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
    assert process["model"]["low_vram"] is True
    assert process["model"]["qtype_te"] == "qfloat8"
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


def test_resolution_uses_toolkit_resolution_list(tmp_path):
    adapted = adapt_config(
        _source(tmp_path, resolution=[512, 768, 1024]),
        _runtime(tmp_path),
        "run-1",
        "klein-4b",
    )
    assert _process(adapted)["datasets"][0]["resolution"] == [512, 768, 1024]


def test_resolution_keeps_legacy_string_compatibility(tmp_path):
    adapted = adapt_config(
        _source(tmp_path, resolution="512,768,1024"),
        _runtime(tmp_path),
        "run-1",
        "klein-4b",
    )
    assert _process(adapted)["datasets"][0]["resolution"] == [512, 768, 1024]


def test_model_quantization_types_are_configured_independently(tmp_path):
    adapted = adapt_config(
        _source(tmp_path, qtype="qint4", qtype_te="qint8", low_vram=False),
        _runtime(tmp_path),
        "run-1",
        "klein-4b",
    )
    model = _process(adapted)["model"]
    assert model["qtype"] == "qint4"
    assert model["qtype_te"] == "qint8"
    assert model["low_vram"] is False


def test_log_dir_defaults_to_runtime(tmp_path):
    adapted = adapt_config(_source(tmp_path), _runtime(tmp_path), "run-1", "klein-4b")
    process = _process(adapted)
    assert process["log_dir"] == (tmp_path / "logs" / "ai-toolkit").as_posix()
    assert process["logging"] == {"log_every": 20}


def test_log_dir_ui_override(tmp_path):
    adapted = adapt_config(_source(tmp_path, logging_dir="my-logs"), _runtime(tmp_path), "run-1", "klein-4b")
    process = _process(adapted)
    assert process["log_dir"] == (tmp_path / "my-logs").resolve().as_posix()


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
    prompts = tmp_path / "prompts.txt"
    prompts.write_text("a cat\n", encoding="utf-8")
    data["sample_prompts"] = str(prompts)
    data["negative_prompts"] = "blurry"
    adapted = adapt_config(data, _runtime(tmp_path), "run-1", "klein-4b")
    assert _process(adapted)["sample"]["neg"] == "blurry"


def test_sample_control_images_map_to_toolkit_sample_fields(tmp_path):
    data = _source(tmp_path, task="image-edit")
    prompts = tmp_path / "prompts.txt"
    prompts.write_text("edit this image\n", encoding="utf-8")
    control_one = tmp_path / "control-one.png"
    control_two = tmp_path / "control-two.jpg"
    control_one.write_bytes(b"png")
    control_two.write_bytes(b"jpg")
    data.update(
        sample_prompts=str(prompts),
        sample_control_images=[str(control_one), str(control_two), ""],
    )

    adapted = adapt_config(data, _runtime(tmp_path), "run-1", "klein-4b")

    sample = _process(adapted)["sample"]
    assert sample["samples"] == [{
        "prompt": "edit this image",
        "ctrl_img_1": control_one.resolve().as_posix(),
        "ctrl_img_2": control_two.resolve().as_posix(),
    }]
    assert "prompts" not in sample


def test_preview_samples_map_each_prompt_and_control_images(tmp_path):
    data = _source(tmp_path, task="image-edit")
    control_one = tmp_path / "control-one.png"
    control_two = tmp_path / "control-two.jpg"
    control_three = tmp_path / "control-three.webp"
    for path in (control_one, control_two, control_three):
        path.write_bytes(b"image")
    data["preview_samples"] = [
        {"prompt": "first edit", "control_images": [str(control_one)]},
        {"prompt": "second edit", "control_images": [str(control_two), str(control_three)]},
    ]

    adapted = adapt_config(data, _runtime(tmp_path), "run-1", "klein-4b")

    assert _process(adapted)["sample"]["samples"] == [
        {
            "prompt": "first edit",
            "width": 1024,
            "height": 1024,
            "seed": 42,
            "guidance_scale": 4.0,
            "sample_steps": 20,
            "network_multiplier": 1.0,
            "sampler": "flowmatch",
            "ctrl_img_1": control_one.resolve().as_posix(),
        },
        {
            "prompt": "second edit",
            "width": 1024,
            "height": 1024,
            "seed": 42,
            "guidance_scale": 4.0,
            "sample_steps": 20,
            "network_multiplier": 1.0,
            "sampler": "flowmatch",
            "ctrl_img_1": control_two.resolve().as_posix(),
            "ctrl_img_2": control_three.resolve().as_posix(),
        },
    ]


def test_preview_samples_accept_frontend_camel_case_control_images(tmp_path):
    data = _source(tmp_path, task="image-edit")
    control_one = tmp_path / "control-one.png"
    control_one.write_bytes(b"image")
    # PreviewSampleField serializes each sample as a JSON string with camelCase keys
    data["preview_samples"] = [json.dumps({"prompt": "edit", "controlImages": [str(control_one)]})]

    adapted = adapt_config(data, _runtime(tmp_path), "run-1", "klein-4b")

    assert _process(adapted)["sample"]["samples"][0]["ctrl_img_1"] == control_one.resolve().as_posix()


def test_preview_samples_map_independent_generation_settings(tmp_path):
    data = _source(tmp_path)
    data["preview_samples"] = [
        {
            "prompt": "first",
            "control_images": [],
            "width": 768,
            "height": 1024,
            "seed": 11,
            "guidance_scale": 3,
            "sample_steps": 18,
            "network_multiplier": 0.8,
            "sampler": "flowmatch",
            "neg": "blurry, low quality",
        }
    ]

    adapted = adapt_config(data, _runtime(tmp_path), "run-1", "klein-4b")

    assert _process(adapted)["sample"]["samples"] == [
        {
            "prompt": "first",
            "width": 768,
            "height": 1024,
            "seed": 11,
            "guidance_scale": 3,
            "sample_steps": 18,
            "network_multiplier": 0.8,
            "sampler": "flowmatch",
            "neg": "blurry, low quality",
        }
    ]


def test_max_grad_norm_mapped(tmp_path):
    adapted = adapt_config(_source(tmp_path), _runtime(tmp_path), "run-1", "klein-4b")
    assert "max_grad_norm" not in _process(adapted)["train"]
    adapted = adapt_config(_source(tmp_path, max_grad_norm=0.5), _runtime(tmp_path), "run-1", "klein-4b")
    assert _process(adapted)["train"]["max_grad_norm"] == pytest.approx(0.5)


def test_control_dirs_blank_rows_ignored(tmp_path):
    ctrl = tmp_path / "control"
    ctrl.mkdir()
    adapted = adapt_config(
        _source(tmp_path, control_data_dirs=[str(ctrl), "", "   "]),
        _runtime(tmp_path),
        "run-1",
        "klein-4b",
    )
    assert _process(adapted)["datasets"][0]["control_path"] == [ctrl.resolve().as_posix()]


def test_control_dirs_non_list_rejected(tmp_path):
    with pytest.raises(AdapterError, match="control_data_dirs"):
        adapt_config(_source(tmp_path, control_data_dirs=123), _runtime(tmp_path), "run-1", "klein-4b")


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


def test_te_path_side_channel(tmp_path):
    adapted = adapt_config(_source(tmp_path), _runtime(tmp_path), "run-1", "klein-4b")
    assert adapted.te_path == (tmp_path / "models" / "qwen3-4b").resolve().as_posix()
    # TE path must NOT leak into the yaml (upstream has no such config key)
    text = dump_yaml(adapted.config)
    assert "qwen3-4b" not in text


def test_missing_te_rejected(tmp_path):
    source = _source(tmp_path)
    source["text_encoder"] = ""
    with pytest.raises(AdapterError, match="文本编码器"):
        adapt_config(source, _runtime(tmp_path), "run-1", "klein-4b")


def test_te_dir_missing_rejected(tmp_path):
    source = _source(tmp_path, text_encoder=str(tmp_path / "nope"))
    with pytest.raises(AdapterError, match="文本编码器目录不存在"):
        adapt_config(source, _runtime(tmp_path), "run-1", "klein-4b")


def test_local_dit_file_maps_to_parent(tmp_path):
    dit = tmp_path / "models" / "flux-2-klein-base-4b.safetensors"
    dit.parent.mkdir(parents=True)
    dit.write_bytes(b"")
    adapted = adapt_config(
        _source(tmp_path, pretrained_model_name_or_path=str(dit)), _runtime(tmp_path), "run-1", "klein-4b"
    )
    assert _process(adapted)["model"]["name_or_path"] == dit.parent.resolve().as_posix()
    assert adapted.warnings == []


def test_local_dit_file_wrong_name_warns(tmp_path):
    dit = tmp_path / "models" / "whatever.safetensors"
    dit.parent.mkdir(parents=True)
    dit.write_bytes(b"")
    adapted = adapt_config(
        _source(tmp_path, pretrained_model_name_or_path=str(dit)), _runtime(tmp_path), "run-1", "klein-4b"
    )
    assert any("不一致" in w for w in adapted.warnings)


def test_explicit_vae_file_is_mapped_to_model_config(tmp_path):
    vae = tmp_path / "assets" / "custom-vae.safetensors"
    vae.parent.mkdir(parents=True)
    vae.write_bytes(b"")

    adapted = adapt_config(_source(tmp_path, vae=str(vae)), _runtime(tmp_path), "run-1", "klein-4b")

    assert _process(adapted)["model"]["vae_path"] == vae.resolve().as_posix()


def test_model_source_directory_keeps_repository_directory(tmp_path):
    model_dir = tmp_path / "models" / "FLUX.2-klein-base-4B"
    model_dir.mkdir(parents=True)

    adapted = adapt_config(
        _source(tmp_path, model_source="local-directory", dit=str(model_dir)),
        _runtime(tmp_path),
        "run-1",
        "klein-4b",
    )

    assert _process(adapted)["model"]["name_or_path"] == model_dir.resolve().as_posix()


def test_model_source_hf_repo_keeps_repository_id(tmp_path):
    adapted = adapt_config(
        _source(tmp_path, model_source="hf-repo", dit="black-forest-labs/FLUX.2-klein-base-4B"),
        _runtime(tmp_path),
        "run-1",
        "klein-4b",
    )

    assert _process(adapted)["model"]["name_or_path"] == "black-forest-labs/FLUX.2-klein-base-4B"


def test_model_source_local_file_missing_path_rejected(tmp_path):
    with pytest.raises(AdapterError, match="本地模型文件"):
        adapt_config(
            _source(tmp_path, model_source="local-file", dit=str(tmp_path / "models" / "missing.safetensors")),
            _runtime(tmp_path),
            "run-1",
            "klein-4b",
        )


def test_model_source_local_directory_missing_path_rejected(tmp_path):
    with pytest.raises(AdapterError, match="本地模型目录"):
        adapt_config(
            _source(tmp_path, model_source="local-directory", dit="models/klein"),
            _runtime(tmp_path),
            "run-1",
            "klein-4b",
        )


def test_model_source_local_file_wrong_filename_rejected(tmp_path):
    dit = tmp_path / "models" / "whatever.safetensors"
    dit.parent.mkdir(parents=True)
    dit.write_bytes(b"")
    with pytest.raises(AdapterError, match="与变体期望的"):
        adapt_config(
            _source(tmp_path, model_source="local-file", dit=str(dit)),
            _runtime(tmp_path),
            "run-1",
            "klein-4b",
        )


def test_model_source_local_file_matching_filename_accepted(tmp_path):
    dit = tmp_path / "models" / "flux-2-klein-base-4b.safetensors"
    dit.parent.mkdir(parents=True)
    dit.write_bytes(b"")
    adapted = adapt_config(
        _source(tmp_path, model_source="local-file", dit=str(dit)),
        _runtime(tmp_path),
        "run-1",
        "klein-4b",
    )
    assert _process(adapted)["model"]["name_or_path"] == dit.parent.resolve().as_posix()


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
    assert _process(adapted)["datasets"][0]["control_path"] == [ctrl.resolve().as_posix()]


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

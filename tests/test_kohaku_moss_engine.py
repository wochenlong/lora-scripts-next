import sys
from pathlib import Path

import pytest

from mikazuki.download_sources import DownloadSources
from mikazuki.engines.kohaku_moss.adapter import adapt_config, dump_config
from mikazuki.engines.kohaku_moss.environment import install_commands
from mikazuki.engines.kohaku_moss.extension_state import read_status, write_state
from mikazuki.engines.kohaku_moss.installer import installation_plan
from mikazuki.engines.kohaku_moss.manifest import ENGINE_ID, TRAIN_TYPES, UPSTREAM
from mikazuki.engines.kohaku_moss.patch_upstream import apply_patch
from mikazuki.engines.kohaku_moss.settings import INSTALL_REVISION, Runtime
from mikazuki.engines.portable_venv import read_venv_home


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


def test_installation_plan_applies_windows_build_fallback_before_dependencies(tmp_path):
    runtime = Runtime(tmp_path)
    commands = installation_plan(runtime, DownloadSources())
    patch_index = next(i for i, command in enumerate(commands) if "patch_upstream.py" in " ".join(command))
    uv_index = next(i for i, command in enumerate(commands) if command[:2] == ["uv", "python"])
    assert patch_index < uv_index


def test_windows_build_fallback_patch_is_idempotent(tmp_path):
    source = tmp_path / "source"
    target = source / "src" / "kohakumoss_kernels" / "errors.py"
    target.parent.mkdir(parents=True)
    target.write_text(
        '"""errors"""\n\nimport torch\n\nBUILD_ERRORS = (\n    RuntimeError,\n    UnicodeError,\n)\n',
        encoding="utf-8",
    )
    assert apply_patch(source) is True
    assert apply_patch(source) is False
    text = target.read_text(encoding="utf-8")
    assert text.count("import subprocess") == 1
    assert text.count("subprocess.CalledProcessError") == 1


def test_packaged_runtime_repairs_moved_python_home(tmp_path):
    runtime = Runtime(tmp_path)
    runtime.python.parent.mkdir(parents=True)
    runtime.python.write_bytes(b"")
    runtime.kogine.write_bytes(b"")
    (runtime.source / "scripts" / "train").mkdir(parents=True)
    (runtime.source / "scripts" / "train" / "moss.py").write_text("", encoding="utf-8")
    (runtime.root / ".venv" / "pyvenv.cfg").write_text(
        "home = Z:\\stale-build\\python\ninclude-system-site-packages = false\n",
        encoding="utf-8",
    )
    base = (
        runtime.python_install_dir / "cpython-3.12.12-windows-x86_64-none" / "python.exe"
        if sys.platform == "win32"
        else runtime.python_install_dir / "cpython-3.12.12-linux-x86_64-gnu" / "bin" / "python3"
    )
    base.parent.mkdir(parents=True)
    base.write_bytes(b"")
    write_state(runtime, "ready", {"install_revision": INSTALL_REVISION})
    status = read_status(runtime)
    assert status["state"] == "ready"
    assert read_venv_home(runtime.python) == base.parent


def _base(tmp_path=None, **overrides):
    config = {
        "model_train_type": "kohaku-moss-image-lora",
        "pretrained_model_name_or_path": "models/MOSS-Image-Base",
        "train_data_dir": "train/moss",
        "output_dir": "output",
        "output_name": "dragon-test",
        "max_train_steps": 20,
        "network_algorithm": "lokr",
        "network_dim": 16,
        "network_preset": "attn-mlp",
        "lokr_factor": 8,
        "lokr_full_matrix": True,
        "memory_profile": "minimal",
        "sample_every_n_steps": 10,
        "sample_prompts": "a dragon girl\nanother prompt",
        "sample_negative": "lowres",
        "sample_width": 1024,
        "sample_height": 768,
        "sample_steps": 20,
        "sample_cfg": 3.5,
        "sample_shift": 5.0,
        "sample_seed": 7,
        "batching": "count",
        "batch_size": 1,
        "latent_cache": "online",
        "text_cache": "online",
        "lr_warmup_steps": 5,
        "optimizer_type": "adamw",
        "grad_acc": 2,
        "tune_mode": "off",
    }
    config.update(overrides)
    return config


def test_adapter_writes_native_kogine_python_config(tmp_path):
    runtime = Runtime(tmp_path)
    adapted = adapt_config(_base(), runtime)
    assert adapted.values["ALGO"] == "lokr"
    assert adapted.values["STEPS"] == 20
    assert adapted.values["PRESET"] == "attn-mlp"
    assert adapted.values["ALGO_KWARGS"]["factor"] == 8
    assert adapted.values["ALGO_KWARGS"]["full_matrix"] is True
    assert adapted.values["BATCHING"] == "count"
    assert adapted.values["BATCH_SIZE"] == 1
    assert adapted.values["GRAD_ACC"] == 2
    assert adapted.values["SCHEDULE"]["warmup"] == 5
    assert adapted.values["TUNE"] == "off"
    assert adapted.values["SAMPLE_EVERY"] == 10
    assert adapted.values["SAMPLE_PROMPTS"] == ["a dragon girl", "another prompt"]
    assert adapted.values["SAMPLE_SIZE"] == (1024, 768)
    path = dump_config(adapted, tmp_path / "autosave", "test")
    text = Path(path).read_text(encoding="utf-8")
    assert "MEMORY_PROFILE = 'minimal'" in text
    assert "EXPORT_FORMATS = ('comfy', 'lycoris')" in text
    assert "SAMPLE_EVERY = 10" in text
    assert "ALGO_KWARGS =" in text
    assert "DROPOUT =" in text


def test_adapter_hides_rank_for_ia3_and_maps_oft_kwargs(tmp_path):
    runtime = Runtime(tmp_path)
    ia3 = adapt_config(_base(network_algorithm="ia3", output_name="ia3-test", sample_every_n_steps=0), runtime)
    assert ia3.values["ALGO"] == "ia3"
    assert ia3.values["DIM"] == 1
    assert ia3.values["ALGO_KWARGS"] == {"train_on_input": False}
    oft = adapt_config(
        _base(
            output_name="oft-test", network_algorithm="oft", network_dim=64,
            oft_constraint=0.1, oft_rescaled=True, network_dora=True, sample_every_n_steps=0,
        ),
        runtime,
    )
    assert oft.values["ALGO_KWARGS"] == {"constraint": 0.1, "rescaled": True}
    assert oft.values["DORA"] is True


def test_adapter_maps_tlora_masks_and_fp8_base(tmp_path):
    runtime = Runtime(tmp_path)
    adapted = adapt_config(
        _base(
            output_name="tlora-test",
            network_algorithm="tlora",
            adapter_mode="bypass",
            tlora_mask_min_rank=2,
            tlora_mask_alpha=1.5,
            base_precision="fp8_compute",
            fp8_recipe="block",
            fp8_dgrad="16bit",
            sample_every_n_steps=0,
        ),
        runtime,
    )
    assert adapted.values["ALGO_KWARGS"]["mask_min_rank"] == 2
    assert adapted.values["ALGO_KWARGS"]["mask_alpha"] == 1.5
    assert adapted.values["BASE_PRECISION"] == "fp8_compute"
    assert adapted.values["FP8_RECIPE"] == "block"
    assert adapted.values["FP8_DGRAD"] == "16bit"


def test_adapter_rejects_warmup_not_less_than_steps(tmp_path):
    runtime = Runtime(tmp_path)
    try:
        adapt_config(_base(lr_warmup_steps=20, max_train_steps=20, sample_every_n_steps=0), runtime)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "lr_warmup_steps" in str(exc)


def test_adapter_supports_comfyui_files_mode(tmp_path):
    runtime = Runtime(tmp_path)
    cfg = _base(
        model_input_mode="comfyui_files",
        pretrained_model_name_or_path="",
        dit_path="models/dit.safetensors",
        text_encoder_path="models/te.safetensors",
        vae_path="models/vae.safetensors",
        tokenizer_path="models/tokenizer",
        sample_every_n_steps=0,
    )
    adapted = adapt_config(cfg, runtime)
    assert adapted.model_input_mode == "comfyui_files"
    assert adapted.staging_root is not None
    assert Path(adapted.values["WEIGHTS"]) == tmp_path / "models" / "dit.safetensors"
    assert Path(adapted.values["TEXT_ENCODER"]) == Path(adapted.staging_root) / "MOSS-Image-Base"
    assert Path(adapted.values["VAE"]) == Path(adapted.staging_root) / "MOSS-Image-Base" / "vae"
    assert adapted.values["DATASETS"][0]["include_root"] is True
    assert adapted.values["DATASETS"][0]["txt_as"] == "nl"
    assert adapted.values["CAPTION"] == {"template": "nl", "keep": ()}
    assert adapted.values["OVERLONG"] == "drop_tokens"
    assert adapted.values["TEXT_ENCODE"]["memory"] == "stream"
    assert any("ComfyUI" in w for w in adapted.warnings)


def test_adapter_resolves_parent_native_directory_for_sft(tmp_path):
    runtime = Runtime(tmp_path)
    root = tmp_path / "moss-root"
    (root / "MOSS-Image-Base" / "transformer").mkdir(parents=True)
    (root / "MOSS-Image-Base" / "text_encoder").mkdir(parents=True)
    (root / "MOSS-Image-Base" / "vae").mkdir(parents=True)
    (root / "MOSS-Image-SFT" / "transformer").mkdir(parents=True)

    adapted = adapt_config(
        _base(
            model_input_mode="native_directory",
            pretrained_model_name_or_path=str(root),
            model_variant="sft",
            caption_mode="tags",
            sample_every_n_steps=0,
        ),
        runtime,
    )
    assert Path(adapted.values["WEIGHTS"]) == root / "MOSS-Image-SFT"
    assert Path(adapted.values["TEXT_ENCODER"]) == root / "MOSS-Image-Base"
    assert Path(adapted.values["VAE"]) == root / "MOSS-Image-Base" / "vae"
    assert adapted.values["DATASETS"][0]["txt_as"] == "tags"
    assert adapted.values["CAPTION"] == {"template": "tags", "shuffle": True, "keep": ()}


def test_config_import_and_dataset_validate_accept_kohaku_moss():
    import mikazuki.app  # noqa: F401
    from mikazuki.datasets.validate import KNOWN_ENGINES
    from mikazuki.utils.config_import import validate_config_import

    assert "kohaku-moss" in KNOWN_ENGINES
    payload = validate_config_import(
        "kohaku-moss-image-lora",
        {
            "model_train_type": "kohaku-moss-image-lora",
            "model_input_mode": "comfyui_files",
            "dit_path": "./sd-models/moss-image/dit.safetensors",
            "network_algorithm": "lokr",
            "memory_profile": "balanced",
            "sample_every_n_steps": 200,
            "sample_prompts": "1girl, solo",
        },
    )
    assert payload["result"] == "ok"
    assert "enable_preview" not in payload["config"]


def test_optim_extra_and_old_installs_need_upgrade(tmp_path):
    runtime = Runtime(tmp_path)
    assert f"{runtime.source}[cuda,optim]" in install_commands(runtime, DownloadSources())[-1]
    for path in (runtime.python, runtime.kogine, runtime.source / 'scripts/train/moss.py'):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    write_state(runtime, 'ready')
    assert read_status(runtime)['state'] == 'installed_unverified'


@pytest.mark.parametrize('precision', ['fp16', 'auto'])
def test_fp16_fix_has_required_scale_and_can_preserve_fixed_weights(tmp_path, precision):
    values = adapt_config(_base(mixed_precision=precision), Runtime(tmp_path)).values
    assert values['FP16_FIX'] == 'online'
    assert values['FP16_FIX_KWARGS'] == {'c': 1 / 16}
    values = adapt_config(_base(mixed_precision=precision, fp16_fix='none'), Runtime(tmp_path)).values
    assert values['FP16_FIX'] == 'none' and values['FP16_FIX_KWARGS'] == {}


@pytest.mark.parametrize('parallel,schedule', [('pipeline', '1f1b'), ('threaded', 'gpipe')])
def test_pipeline_has_native_companion_parameters(tmp_path, monkeypatch, parallel, schedule):
    monkeypatch.setattr(sys, 'platform', 'linux')
    values = adapt_config(_base(parallel_mode=parallel, devices='0,1', memory_profile='speed',
                                batching='tokens', max_samples=4, text_cache='offline',
                                sample_every_n_steps=0), Runtime(tmp_path)).values
    assert values['PIPELINE_SCHEDULE'] == schedule
    assert values['MICROBATCHES'] == 4
    if parallel == 'pipeline':
        assert values['TOKEN_BUDGET'] == 'exact'


@pytest.mark.parametrize('overrides,field', [
    ({'lr_schedule_end': 4}, 'lr_warmup_steps'),
    ({'devices': '0,1'}, 'devices'),
    ({'devices': '2', 'gpu_ids': ['2']}, 'devices'),
    ({'gpu_ids': '0,1'}, 'gpu_ids'),
    ({'optimizer_type': 'prodigy'}, 'optimizer_type'),
    ({'network_alpha': float('nan')}, 'network_alpha'),
    ({'parallel_mode': 'threaded'}, 'memory_profile'),
    ({'parallel_mode': 'threaded', 'memory_profile': 'speed'}, 'sample_every_n_steps'),
    ({'parallel_mode': 'pipeline', 'memory_profile': 'speed', 'sample_every_n_steps': 0}, 'text_cache'),
    ({'parallel_mode': 'threaded', 'memory_profile': 'speed', 'sample_every_n_steps': 0,
      'pipeline_schedule': '1f1b'}, 'pipeline_schedule'),
])
def test_invalid_native_combinations_fail_before_launch(tmp_path, monkeypatch, overrides, field):
    monkeypatch.setattr(sys, 'platform', 'linux')
    with pytest.raises(ValueError, match=field):
        adapt_config(_base(**overrides), Runtime(tmp_path))


def test_windows_multigpu_is_an_error_not_a_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'win32')
    with pytest.raises(ValueError, match='Linux'):
        adapt_config(_base(parallel_mode='ddp'), Runtime(tmp_path))

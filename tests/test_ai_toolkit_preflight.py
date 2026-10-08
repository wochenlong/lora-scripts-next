"""ai-toolkit preflight: per-variant asset checks (DiT/TE/VAE, dataset)."""

from pathlib import Path
import json
import struct

import pytest
from PIL import Image

from mikazuki.engines.ai_toolkit.adapter import AdapterError, adapt_config
from mikazuki.engines.ai_toolkit.preflight import ProbeFacts, run_preflight
from mikazuki.engines.ai_toolkit.settings import RuntimeConfig


def _runtime(tmp_path: Path) -> RuntimeConfig:
    python = tmp_path / "toolkit" / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("")
    (tmp_path / "toolkit" / "run.py").write_text("", encoding="utf-8")
    return RuntimeConfig(
        toolkit_root=tmp_path / "toolkit",
        python=python,
        lora_next_root=tmp_path,
        output_dir=tmp_path / "output",
        logging_dir=tmp_path / "logs",
        cache_dir=tmp_path / ".cache",
    )


def _ok_probe(runtime: RuntimeConfig) -> ProbeFacts:
    return ProbeFacts(
        python_version="3.11.9",
        torch_version="2.13.0+cu130",
        cuda_available=True,
        cuda_version="13.0",
        gpu_name="GB10",
        vram_total_mb=122880,
        transformers_version="5.5.3",
    )


def _weights(path: Path):
    header = json.dumps({"weight": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}}).encode()
    header += b" " * (-len(header) % 8)
    path.write_bytes(struct.pack("<Q", len(header)) + header + struct.pack("<f", 0))


def _setup(tmp_path: Path, with_dit: bool = True, with_vae: bool = True, with_te: bool = True) -> dict:
    data = tmp_path / "train" / "klein"
    data.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8)).save(data / "img1.png")
    (data / "img1.txt").write_text("a cat", encoding="utf-8")
    dit_dir = tmp_path / "models"
    dit_dir.mkdir(exist_ok=True)
    if with_dit:
        _weights(dit_dir / "flux-2-klein-base-4b.safetensors")
    if with_vae:
        _weights(dit_dir / "ae.safetensors")
    te_dir = dit_dir / "qwen3-4b"
    if with_te:
        te_dir.mkdir(exist_ok=True)
        (te_dir / "config.json").write_text('{"hidden_size": 2560}', encoding="utf-8")
        (te_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
        (te_dir / "tokenizer_config.json").write_text("{}", encoding="utf-8")
        _weights(te_dir / "model.safetensors")
    return {
        "pretrained_model_name_or_path": str(dit_dir),
        "text_encoder": str(te_dir),
        "train_data_dir": str(data),
        "max_train_steps": 100,
    }


def test_preflight_ok(tmp_path):
    runtime = _runtime(tmp_path)
    adapted = adapt_config(_setup(tmp_path), runtime, "run-1", "klein-4b")
    result = run_preflight(adapted.config, runtime, "klein-4b", te_path=adapted.te_path, probe=_ok_probe)
    assert result.ok, result.errors
    assert result.facts["dataset_image_count"] == 1
    assert result.facts["model_assets"]["text_encoder"] == adapted.te_path
    assert result.facts["cuda_available"] is True


def test_preflight_missing_local_dit_path_is_error(tmp_path):
    """A typo'd local path is not an HF repo id; it must fail the hard gate."""
    runtime = _runtime(tmp_path)
    source = _setup(tmp_path)
    source["pretrained_model_name_or_path"] = "./sd-models/klein/typo.safetensors"
    with pytest.raises(AdapterError, match="本地路径"):
        adapt_config(source, runtime, "run-1", "klein-4b")


def test_preflight_te_variant_mismatch_is_error(tmp_path):
    runtime = _runtime(tmp_path)
    source = _setup(tmp_path)
    te_dir = Path(source["text_encoder"])
    (te_dir / "config.json").write_text('{"hidden_size": 4096}', encoding="utf-8")
    adapted = adapt_config(source, runtime, "run-1", "klein-4b")
    result = run_preflight(adapted.config, runtime, "klein-4b", te_path=adapted.te_path, probe=_ok_probe)
    assert not result.ok
    assert any("hidden_size=2560" in e for e in result.errors)

    (te_dir / "config.json").write_text('{"hidden_size": 2560}', encoding="utf-8")
    result = run_preflight(adapted.config, runtime, "klein-4b", te_path=adapted.te_path, probe=_ok_probe)
    assert result.ok, result.errors
    assert not any("hidden_size" in w for w in result.warnings)


def test_preflight_missing_dit(tmp_path):
    runtime = _runtime(tmp_path)
    adapted = adapt_config(_setup(tmp_path), runtime, "run-1", "klein-4b")
    # Assets can disappear after adaptation; preflight must recheck them.
    (tmp_path / "models" / "flux-2-klein-base-4b.safetensors").unlink()
    result = run_preflight(adapted.config, runtime, "klein-4b", te_path=adapted.te_path, probe=_ok_probe)
    assert not result.ok
    assert any("flux-2-klein-base-4b.safetensors" in e for e in result.errors)


def test_preflight_missing_vae_is_error(tmp_path):
    runtime = _runtime(tmp_path)
    adapted = adapt_config(_setup(tmp_path, with_vae=False), runtime, "run-1", "klein-4b")
    result = run_preflight(adapted.config, runtime, "klein-4b", te_path=adapted.te_path, probe=_ok_probe)
    assert not result.ok
    assert any("ae.safetensors" in e for e in result.errors)


def test_preflight_missing_te_weights_is_error(tmp_path):
    runtime = _runtime(tmp_path)
    source = _setup(tmp_path)
    te_dir = Path(source["text_encoder"])
    (te_dir / "model.safetensors").unlink()
    adapted = adapt_config(source, runtime, "run-1", "klein-4b")
    result = run_preflight(adapted.config, runtime, "klein-4b", te_path=adapted.te_path, probe=_ok_probe)
    assert not result.ok
    assert any("safetensors" in e for e in result.errors)


def test_preflight_hf_repo_rejected_before_probe(tmp_path):
    runtime = _runtime(tmp_path)
    source = _setup(tmp_path)
    source["pretrained_model_name_or_path"] = "black-forest-labs/FLUX.2-klein-base-4B"
    with pytest.raises(AdapterError, match="不会自动下载或转换"):
        adapt_config(source, runtime, "run-1", "klein-4b")


def test_preflight_missing_python(tmp_path):
    runtime = _runtime(tmp_path)
    (runtime.python).unlink()
    adapted = adapt_config(_setup(tmp_path), runtime, "run-1", "klein-4b")
    result = run_preflight(adapted.config, runtime, "klein-4b", te_path=adapted.te_path, probe=_ok_probe)
    assert not result.ok
    assert any("python 不存在" in e for e in result.errors)


def test_preflight_missing_caption_uses_empty_manifest_caption(tmp_path):
    runtime = _runtime(tmp_path)
    source = _setup(tmp_path)
    data = Path(source["train_data_dir"])
    Image.new("RGB", (8, 8)).save(data / "img2.png")  # no img2.txt
    adapted = adapt_config(source, runtime, "run-1", "klein-4b")
    result = run_preflight(adapted.config, runtime, "klein-4b", te_path=adapted.te_path, probe=_ok_probe)
    assert result.ok, result.errors
    assert result.facts["dataset_image_count"] == 2
    manifest = next(iter(adapted.dataset_manifests.values()))
    assert manifest[str(data / "img1.png")]["caption"] == "a cat"
    assert manifest[str(data / "img2.png")]["caption"] == ""


def test_preflight_probe_no_cuda(tmp_path):
    runtime = _runtime(tmp_path)

    def no_cuda(runtime: RuntimeConfig) -> ProbeFacts:
        return ProbeFacts(cuda_available=False)

    adapted = adapt_config(_setup(tmp_path), runtime, "run-1", "klein-4b")
    result = run_preflight(adapted.config, runtime, "klein-4b", te_path=adapted.te_path, probe=no_cuda)
    assert not result.ok
    assert any("CUDA" in e for e in result.errors)


@pytest.mark.parametrize("asset", ["flux-2-klein-base-4b.safetensors", "ae.safetensors",
                                  "qwen3-4b/model.safetensors"])
def test_preflight_invalid_weights_rejected_before_probe(tmp_path, asset):
    runtime = _runtime(tmp_path)
    adapted = adapt_config(_setup(tmp_path), runtime, "run-1", "klein-4b")
    (tmp_path / "models" / asset).write_bytes(b"invalid weights")

    def unexpected_probe(runtime):
        pytest.fail("Invalid assets must fail before the dependency probe")

    result = run_preflight(adapted.config, runtime, "klein-4b", probe=unexpected_probe)
    assert not result.ok
    assert any("safetensors" in error for error in result.errors)


def test_preflight_missing_te_directory_is_error(tmp_path):
    runtime = _runtime(tmp_path)
    adapted = adapt_config(_setup(tmp_path, with_te=False), runtime, "run-1", "klein-4b")
    result = run_preflight(adapted.config, runtime, "klein-4b", probe=_ok_probe)
    assert not result.ok
    assert any("config.json" in error for error in result.errors)


def test_preflight_missing_startup_script_is_error(tmp_path):
    runtime = _runtime(tmp_path)
    adapted = adapt_config(_setup(tmp_path), runtime, "run-1", "klein-4b")
    (runtime.toolkit_root / "run.py").unlink()
    result = run_preflight(adapted.config, runtime, "klein-4b", probe=_ok_probe)
    assert not result.ok
    assert any("run.py" in error for error in result.errors)

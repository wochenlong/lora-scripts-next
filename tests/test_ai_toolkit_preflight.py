"""ai-toolkit preflight: per-variant asset checks (DiT/TE/VAE, dataset)."""

from pathlib import Path

from mikazuki.engines.ai_toolkit.adapter import adapt_config
from mikazuki.engines.ai_toolkit.preflight import ProbeFacts, run_preflight
from mikazuki.engines.ai_toolkit.settings import RuntimeConfig


def _runtime(tmp_path: Path) -> RuntimeConfig:
    python = tmp_path / "toolkit" / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("")
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


def _setup(tmp_path: Path, with_dit: bool = True, with_vae: bool = True, with_te: bool = True) -> dict:
    data = tmp_path / "train" / "klein"
    data.mkdir(parents=True, exist_ok=True)
    (data / "img1.png").write_bytes(b"")
    (data / "img1.txt").write_text("a cat", encoding="utf-8")
    dit_dir = tmp_path / "models"
    dit_dir.mkdir(exist_ok=True)
    if with_dit:
        (dit_dir / "flux-2-klein-base-4b.safetensors").write_bytes(b"")
    if with_vae:
        (dit_dir / "ae.safetensors").write_bytes(b"")
    te_dir = dit_dir / "qwen3-4b"
    if with_te:
        te_dir.mkdir(exist_ok=True)
        (te_dir / "config.json").write_text("{}", encoding="utf-8")
        (te_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
        (te_dir / "tokenizer_config.json").write_text("{}", encoding="utf-8")
        (te_dir / "model.safetensors").write_bytes(b"")
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
    assert result.facts["text_encoder"] == adapted.te_path


def test_preflight_missing_local_dit_path_is_error(tmp_path):
    """A typo'd local path is not an HF repo id; it must fail the hard gate."""
    runtime = _runtime(tmp_path)
    source = _setup(tmp_path)
    source["pretrained_model_name_or_path"] = "./sd-models/klein/typo.safetensors"
    adapted = adapt_config(source, runtime, "run-1", "klein-4b")
    result = run_preflight(adapted.config, runtime, "klein-4b", te_path=adapted.te_path, probe=_ok_probe)
    assert not result.ok
    assert any("HF repo id" in e for e in result.errors)


def test_preflight_te_variant_mismatch_is_error(tmp_path):
    runtime = _runtime(tmp_path)
    source = _setup(tmp_path)
    te_dir = Path(source["text_encoder"])
    (te_dir / "config.json").write_text('{"hidden_size": 4096}', encoding="utf-8")
    adapted = adapt_config(source, runtime, "run-1", "klein-4b")
    result = run_preflight(adapted.config, runtime, "klein-4b", te_path=adapted.te_path, probe=_ok_probe)
    assert not result.ok
    assert any("hidden_size" in e for e in result.errors)

    (te_dir / "config.json").write_text('{"hidden_size": 2560}', encoding="utf-8")
    result = run_preflight(adapted.config, runtime, "klein-4b", te_path=adapted.te_path, probe=_ok_probe)
    assert result.ok, result.errors
    assert not any("hidden_size" in e for e in result.errors)

    # hidden_size unreadable stays a soft case: no hard error
    (te_dir / "config.json").write_text('{"n": "o hidden"}', encoding="utf-8")
    result = run_preflight(adapted.config, runtime, "klein-4b", te_path=adapted.te_path, probe=_ok_probe)
    assert result.ok, result.errors


def test_preflight_missing_dit(tmp_path):
    runtime = _runtime(tmp_path)
    adapted = adapt_config(_setup(tmp_path, with_dit=False), runtime, "run-1", "klein-4b")
    result = run_preflight(adapted.config, runtime, "klein-4b", te_path=adapted.te_path, probe=_ok_probe)
    assert not result.ok
    assert any("flux-2-klein-base-4b.safetensors" in e for e in result.errors)


def test_preflight_missing_vae_is_error(tmp_path):
    runtime = _runtime(tmp_path)
    adapted = adapt_config(_setup(tmp_path, with_vae=False), runtime, "run-1", "klein-4b")
    result = run_preflight(adapted.config, runtime, "klein-4b", te_path=adapted.te_path, probe=_ok_probe)
    assert not result.ok
    assert any("ae.safetensors" in e for e in result.errors)


def test_preflight_accepts_explicit_vae_path_outside_dit_directory(tmp_path):
    source = _setup(tmp_path, with_vae=False)
    vae = tmp_path / "assets" / "custom-vae.safetensors"
    vae.parent.mkdir(parents=True)
    vae.write_bytes(b"")
    source["vae"] = str(vae)

    adapted = adapt_config(source, _runtime(tmp_path), "run-1", "klein-4b")
    result = run_preflight(adapted.config, _runtime(tmp_path), "klein-4b", te_path=adapted.te_path, probe=_ok_probe)

    assert result.ok, result.errors
    assert result.facts["vae"] == vae.resolve().as_posix()


def test_preflight_missing_te_weights_is_error(tmp_path):
    runtime = _runtime(tmp_path)
    source = _setup(tmp_path)
    te_dir = Path(source["text_encoder"])
    (te_dir / "model.safetensors").unlink()
    adapted = adapt_config(source, runtime, "run-1", "klein-4b")
    result = run_preflight(adapted.config, runtime, "klein-4b", te_path=adapted.te_path, probe=_ok_probe)
    assert not result.ok
    assert any("safetensors" in e for e in result.errors)


def test_preflight_hf_repo_warns_not_errors(tmp_path):
    runtime = _runtime(tmp_path)
    source = _setup(tmp_path)
    source["pretrained_model_name_or_path"] = "black-forest-labs/FLUX.2-klein-base-4B"
    adapted = adapt_config(source, runtime, "run-1", "klein-4b")
    result = run_preflight(adapted.config, runtime, "klein-4b", te_path=adapted.te_path, probe=_ok_probe)
    assert result.ok, result.errors
    assert any("HF" in w for w in result.warnings)


def test_preflight_missing_python(tmp_path):
    runtime = _runtime(tmp_path)
    (runtime.python).unlink()
    adapted = adapt_config(_setup(tmp_path), runtime, "run-1", "klein-4b")
    result = run_preflight(adapted.config, runtime, "klein-4b", te_path=adapted.te_path, probe=_ok_probe)
    assert not result.ok
    assert any("python 不存在" in e for e in result.errors)


def test_preflight_caption_warning(tmp_path):
    runtime = _runtime(tmp_path)
    source = _setup(tmp_path)
    data = Path(source["train_data_dir"])
    (data / "img2.png").write_bytes(b"")  # no img2.txt
    adapted = adapt_config(source, runtime, "run-1", "klein-4b")
    result = run_preflight(adapted.config, runtime, "klein-4b", te_path=adapted.te_path, probe=_ok_probe)
    assert result.ok
    assert any("caption" in w for w in result.warnings)


def test_preflight_control_pairing_ok(tmp_path):
    runtime = _runtime(tmp_path)
    source = _setup(tmp_path)
    control = tmp_path / "control"
    control.mkdir()
    (control / "img1.png").write_bytes(b"")
    source["control_data_dirs"] = [str(control)]
    adapted = adapt_config(source, runtime, "run-1", "klein-4b")
    result = run_preflight(adapted.config, runtime, "klein-4b", te_path=adapted.te_path, probe=_ok_probe)
    assert result.ok, result.errors


def test_preflight_control_pairing_accepts_different_extension(tmp_path):
    runtime = _runtime(tmp_path)
    source = _setup(tmp_path)
    control = tmp_path / "control"
    control.mkdir()
    (control / "img1.jpg").write_bytes(b"")  # same stem, different extension
    source["control_data_dirs"] = [str(control)]
    adapted = adapt_config(source, runtime, "run-1", "klein-4b")
    result = run_preflight(adapted.config, runtime, "klein-4b", te_path=adapted.te_path, probe=_ok_probe)
    assert result.ok, result.errors


def test_preflight_control_pairing_missing_reference_is_error(tmp_path):
    runtime = _runtime(tmp_path)
    source = _setup(tmp_path)
    control = tmp_path / "control"
    control.mkdir()
    (control / "other.png").write_bytes(b"")  # no img1 counterpart
    source["control_data_dirs"] = [str(control)]
    adapted = adapt_config(source, runtime, "run-1", "klein-4b")
    result = run_preflight(adapted.config, runtime, "klein-4b", te_path=adapted.te_path, probe=_ok_probe)
    assert not result.ok
    assert any("同名配对" in e and "img1.png" in e for e in result.errors)


def test_preflight_probe_no_cuda(tmp_path):
    runtime = _runtime(tmp_path)

    def no_cuda(runtime: RuntimeConfig) -> ProbeFacts:
        return ProbeFacts(cuda_available=False)

    adapted = adapt_config(_setup(tmp_path), runtime, "run-1", "klein-4b")
    result = run_preflight(adapted.config, runtime, "klein-4b", te_path=adapted.te_path, probe=no_cuda)
    assert not result.ok
    assert any("CUDA" in e for e in result.errors)

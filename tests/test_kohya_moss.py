from pathlib import Path
from types import SimpleNamespace

import toml

from mikazuki.engines.runner import RunContext


def test_kohya_moss_submission_uses_vendor_launcher_and_safe_defaults(tmp_path, monkeypatch):
    import mikazuki.app.application  # noqa: F401 - initialize app modules before the engine hook
    from mikazuki.engines.kohya import extension_state, run, settings

    dataset = tmp_path / "train" / "1_moss"
    dataset.mkdir(parents=True)
    (dataset / "sample.png").write_bytes(b"image")
    dit = tmp_path / "dit-00001-of-00004.safetensors"
    text_encoder = tmp_path / "text-00001-of-00004.safetensors"
    vae = tmp_path / "vae.safetensors"
    tokenizer = tmp_path / "tokenizer"
    for path in (dit, text_encoder, vae):
        path.write_bytes(b"checkpoint")
    tokenizer.mkdir()

    runtime = SimpleNamespace(python=tmp_path / "python.exe")
    monkeypatch.setattr(settings, "runtime", lambda: runtime)
    monkeypatch.setattr(extension_state, "read_status", lambda _runtime: {"state": "ready"})
    captured = {}

    def fake_run_train(config_path, trainer_file, gpu_ids, cpu_threads, **kwargs):
        captured.update(
            config_path=config_path,
            trainer_file=trainer_file,
            gpu_ids=gpu_ids,
            cpu_threads=cpu_threads,
            kwargs=kwargs,
        )
        return {"ok": True}

    monkeypatch.setattr(run.process, "run_train", fake_run_train)
    config = {
        "model_train_type": "moss-image-lora",
        "train_data_dir": str(dataset.parent),
        "pretrained_model_name_or_path": str(dit),
        "text_encoder": str(text_encoder),
        "vae": str(vae),
        "tokenizer_cache_dir": str(tokenizer),
        "output_dir": str(tmp_path / "output"),
        "output_name": "moss",
    }
    result = run.handle_run(
        config,
        RunContext(
            timestamp="moss-test",
            autosave_dir=str(tmp_path),
            model_train_type="moss-image-lora",
            gpu_ids=["0"],
        ),
    )

    assert result == {"ok": True}
    assert captured["trainer_file"] == "./scripts/dev/moss_image_train_network.py"
    saved = toml.load(captured["config_path"])
    assert saved["network_module"] == "networks.lora_generic"
    assert saved["network_train_unet_only"] is True
    assert saved["caption_extension"] == ".txt"
    assert saved["cache_latents"] is True
    assert saved["cache_latents_to_disk"] is True
    assert saved["cache_text_encoder_outputs"] is True
    assert saved["cache_text_encoder_outputs_to_disk"] is True

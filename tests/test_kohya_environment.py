from pathlib import Path


def test_kohya_training_environment_includes_scipy():
    from mikazuki.engines.kohya.environment import TRAINING_DEPS

    assert any(item == "scipy" or item.startswith("scipy=") for item in TRAINING_DEPS)


def test_kohya_training_environment_includes_moss_compatible_stack():
    from mikazuki.engines.kohya.environment import TRAINING_DEPS

    assert "accelerate==1.15.0" in TRAINING_DEPS
    assert "transformers==5.17.0" in TRAINING_DEPS
    assert "diffusers[torch]==0.40.0" in TRAINING_DEPS
    assert "safetensors==0.8.0" in TRAINING_DEPS
    assert "huggingface-hub==1.32.0" in TRAINING_DEPS
    assert "tokenizers==0.22.2" in TRAINING_DEPS


def test_kohya_install_plan_installs_scipy(tmp_path):
    from mikazuki.download_sources import DownloadSources
    from mikazuki.engines.kohya.environment import install_commands
    from mikazuki.engines.kohya.settings import Runtime

    commands = install_commands(Runtime(Path(tmp_path)), DownloadSources())
    assert any("scipy" in command for command in commands)


def test_kohya_audit_checks_scipy():
    from mikazuki.engines.kohya.environment import audit_environment

    source = audit_environment.__code__.co_consts
    assert any("scipy" in value for value in source if isinstance(value, str))

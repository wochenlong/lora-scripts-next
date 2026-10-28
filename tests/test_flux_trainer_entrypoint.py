from mikazuki.app import application as _application
from mikazuki.engines.kohya.run import TRAINER_MAPPING, _apply_flux_lycoris_compatibility


def test_flux_lora_uses_vendored_trainer():
    assert TRAINER_MAPPING["flux-lora"] == "./vendor/sd-scripts/flux_train_network.py"


def test_flux_lycoris_disables_fp8_base():
    config = {"network_module": "lycoris.kohya", "fp8_base": True}

    _apply_flux_lycoris_compatibility(config, "flux-lora")

    assert config["fp8_base"] is False


def test_flux_plain_lora_keeps_fp8_base():
    config = {"network_module": "networks.lora_flux", "fp8_base": True}

    _apply_flux_lycoris_compatibility(config, "flux-lora")

    assert config["fp8_base"] is True

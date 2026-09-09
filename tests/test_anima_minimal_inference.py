from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
from unittest import TestCase, mock

import torch


VENDOR_DIR = Path(__file__).resolve().parents[1] / "vendor" / "sd-scripts"
sys.path.insert(0, str(VENDOR_DIR))
import anima_minimal_inference as inference  # noqa: E402


class _FakeModel:
    def to(self, *args, **kwargs):
        return self

    def eval(self):
        return self

    def requires_grad_(self, value):
        return self


class _FakeNetwork:
    def __init__(self, merges):
        self._merges = merges

    def merge_to(self, text_encoder, unet, weights_sd, dtype, device):
        self._merges.append((weights_sd, dtype, device))


def _args(*, lycoris, lora_weight=None, lora_multiplier=1.0):
    return SimpleNamespace(
        lycoris=lycoris,
        lora_weight=lora_weight,
        lora_multiplier=lora_multiplier,
        fp8_scaled=False,
        dit="dit.safetensors",
        attn_mode="torch",
    )


class AnimaMinimalInferenceTests(TestCase):
    def test_lycoris_merges_each_weight_once_and_fills_missing_multipliers(self):
        weights = {"one.safetensors": {"one": torch.tensor(1)}, "two.safetensors": {"two": torch.tensor(2)}}
        loaded = []
        network_calls = []
        merges = []
        model = _FakeModel()

        def fake_load_file(path):
            loaded.append(path)
            return weights[path]

        def fake_create_network(**kwargs):
            network_calls.append(kwargs)
            return _FakeNetwork(merges), None

        with (
            mock.patch.object(inference, "load_file", side_effect=fake_load_file),
            mock.patch.object(inference, "create_network_from_weights", side_effect=fake_create_network),
            mock.patch.object(inference.anima_utils, "load_anima_model", return_value=model),
            mock.patch.object(inference, "clean_memory_on_device"),
        ):
            result = inference.load_dit_model(
                _args(
                    lycoris=True,
                    lora_weight=list(weights),
                    lora_multiplier=[0.5],
                ),
                torch.device("cpu"),
            )

        self.assertIs(result, model)
        self.assertEqual(loaded, list(weights))
        self.assertEqual([call["multiplier"] for call in network_calls], [0.5, 1.0])
        self.assertEqual([call["file"] for call in network_calls], [None, None])
        self.assertEqual([call["weights_sd"] for call in network_calls], list(weights.values()))
        self.assertEqual([merge[0] for merge in merges], list(weights.values()))

    def test_non_lycoris_path_still_passes_loaded_weights_to_model_loader(self):
        loaded = {"one": {"lora_unet_one": torch.tensor(1)}}
        model = _FakeModel()

        with (
            mock.patch.object(inference, "load_file", return_value=loaded["one"]),
            mock.patch.object(inference.anima_utils, "load_anima_model", return_value=model) as load_model,
            mock.patch.object(inference, "clean_memory_on_device"),
        ):
            inference.load_dit_model(_args(lycoris=False, lora_weight=["one"]), torch.device("cpu"))

        self.assertEqual(load_model.call_args.kwargs["lora_weights_list"], [loaded["one"]])

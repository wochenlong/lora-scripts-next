import unittest
import sys
import types
from unittest import mock

stub_interrogator = types.ModuleType("mikazuki.tagger.interrogator")
stub_interrogator.available_interrogators = {}
stub_jobs = types.ModuleType("mikazuki.tagger.jobs")
stub_jobs.run_interrogate_job = lambda *args, **kwargs: None
stub_jobs.run_prefetch_job = lambda *args, **kwargs: None
stub_progress = types.ModuleType("mikazuki.tagger.progress")
stub_progress.tagger_progress = types.SimpleNamespace(
    get=lambda: {},
    request_cancel=lambda: False,
    is_busy=lambda: False,
    reset_idle=lambda message=None: None,
)
sys.modules["mikazuki.tagger.interrogator"] = stub_interrogator
sys.modules["mikazuki.tagger.jobs"] = stub_jobs
sys.modules["mikazuki.tagger.progress"] = stub_progress

from mikazuki.app.api import (
    apply_anima_training_defaults,
    normalize_custom_args,
    sanitize_config,
)
from mikazuki.utils.train_utils import fix_config_types


class AnimaTrainingDefaultsTests(unittest.TestCase):
    def test_schema_notes_lokr_train_norm_guardrail(self):
        from pathlib import Path

        schema = (Path(__file__).resolve().parents[1] / "mikazuki" / "schema" / "shared.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("Anima LoKr", schema)
        self.assertIn("train_norm", schema)

    def test_anima_does_not_auto_enable_full_bf16_for_non_lokr(self):
        config = {
            "mixed_precision": "bf16",
            "optimizer_type": "AdamW8bit",
            "lora_type": "lora",
            "unet_lr": "5e-5",
            "attn_mode": "torch",
        }

        apply_anima_training_defaults(config, "anima-lora")

        self.assertNotIn("full_bf16", config)
        self.assertEqual(config["unet_lr"], 5e-5)

    def test_anima_auto_enables_full_bf16_for_lokr_bf16(self):
        config = {
            "mixed_precision": "bf16",
            "optimizer_type": "AdamW8bit",
            "network_module": "lycoris.kohya",
            "network_args": ["algo=lokr", "factor=8"],
            "unet_lr": "5e-5",
            "attn_mode": "torch",
        }

        apply_anima_training_defaults(config, "anima-lora")

        self.assertTrue(config.get("full_bf16"))
        self.assertIn("Enabled full_bf16 for Anima LoKr", config["_training_warnings"][0])

    def test_anima_lokr_full_matrix_uses_conservative_guardrails(self):
        config = {
            "mixed_precision": "bf16",
            "full_bf16": True,
            "optimizer_type": "AdamW8bit",
            "network_module": "lycoris.kohya",
            "network_args": ["algo=lokr", "full_matrix=True"],
            "unet_lr": "5e-5",
            "attn_mode": "torch",
        }

        apply_anima_training_defaults(config, "anima-lora")

        self.assertNotIn("full_bf16", config)
        self.assertEqual(config["scale_weight_norms"], 1)
        self.assertIn("full_matrix=true", config["_training_warnings"][0])

    def test_anima_disables_full_bf16_for_came(self):
        config = {
            "mixed_precision": "bf16",
            "full_bf16": True,
            "optimizer_type": "pytorch_optimizer.CAME",
            "unet_lr": "2e-5",
            "attn_mode": "torch",
        }

        apply_anima_training_defaults(config, "anima-lora")

        self.assertNotIn("full_bf16", config)
        self.assertEqual(config["unet_lr"], 2e-5)
        self.assertIn("pytorch_optimizer.CAME", config["_training_warnings"][0])

    def test_anima_came_lokr_full_matrix_keeps_scale_weight_guardrail(self):
        config = {
            "mixed_precision": "fp16",
            "full_fp16": True,
            "optimizer_type": "pytorch_optimizer.CAME",
            "network_module": "lycoris.kohya",
            "network_args": ["algo=lokr", "full_matrix=True"],
            "unet_lr": "2e-5",
            "attn_mode": "torch",
        }

        with mock.patch("mikazuki.app.api._cuda_bf16_supported", return_value=True):
            apply_anima_training_defaults(config, "anima-lora")

        self.assertEqual(config["mixed_precision"], "bf16")
        self.assertNotIn("full_fp16", config)
        self.assertEqual(config["scale_weight_norms"], 1)
        self.assertTrue(
            any("full_matrix=true" in warning for warning in config["_training_warnings"])
        )

    def test_anima_disables_full_bf16_for_automagic(self):
        config = {
            "mixed_precision": "bf16",
            "full_bf16": True,
            "optimizer_type": "Automagic",
            "unet_lr": "1e-6",
            "attn_mode": "torch",
        }

        apply_anima_training_defaults(config, "anima-lora")

        self.assertNotIn("full_bf16", config)
        self.assertEqual(config["unet_lr"], 1e-6)

    def test_anima_uses_bf16_instead_of_fp16_for_came_when_supported(self):
        config = {
            "mixed_precision": "fp16",
            "full_fp16": True,
            "optimizer_type": "pytorch_optimizer.CAME",
            "unet_lr": "2e-5",
            "attn_mode": "torch",
        }

        with mock.patch("mikazuki.app.api._cuda_bf16_supported", return_value=True):
            apply_anima_training_defaults(config, "anima-lora")

        self.assertEqual(config["mixed_precision"], "bf16")
        self.assertNotIn("full_fp16", config)
        self.assertIn("Changed Anima mixed_precision", config["_training_warnings"][0])

    def test_anima_keeps_fp16_when_bf16_is_not_supported(self):
        config = {
            "mixed_precision": "fp16",
            "optimizer_type": "Automagic",
            "unet_lr": "1e-6",
            "attn_mode": "torch",
        }

        with mock.patch("mikazuki.app.api._cuda_bf16_supported", return_value=False):
            apply_anima_training_defaults(config, "anima-lora")

        self.assertEqual(config["mixed_precision"], "fp16")

    def test_finetune_maps_legacy_unet_lr_to_learning_rate(self):
        config = {
            "unet_lr": "0.0001",
            "optimizer_type": "AdamW8bit",
            "attn_mode": "torch",
        }

        apply_anima_training_defaults(config, "anima-finetune")

        self.assertEqual(config["learning_rate"], "1e-5")
        self.assertNotIn("unet_lr", config)

    def test_finetune_keeps_explicit_learning_rate(self):
        config = {
            "learning_rate": "2e-5",
            "unet_lr": "5e-5",
            "optimizer_type": "AdamW8bit",
            "attn_mode": "torch",
        }

        apply_anima_training_defaults(config, "anima-finetune")

        self.assertEqual(config["learning_rate"], "2e-5")
        self.assertNotIn("unet_lr", config)

    def test_config_sanitize_drops_invalid_custom_args_before_toml(self):
        config = {
            "network_args": [
                "algo=lokr",
                "dropout=undefined",
                "empty=",
                "factor=8",
                "factor=16",
            ],
            "network_args_custom": ["rank=null", "alpha=NaN", "full_matrix=True"],
            "optimizer_args": ["weight_decay=", "eps=nan"],
            "optimizer_args_custom": ["betas=0.9,0.99"],
            "guidance_scale": float("nan"),
            "sigmoid_scale": float("inf"),
            "discrete_flow_shift": "undefined",
            "qwen3": r"C:\models\qwen3",
        }

        normalize_custom_args(config)
        sanitize_config(config)

        self.assertEqual(
            config["network_args"],
            ["algo=lokr", "factor=16", "full_matrix=True"],
        )
        self.assertEqual(config["optimizer_args"], ["betas=0.9,0.99"])
        self.assertNotIn("network_args_custom", config)
        self.assertNotIn("optimizer_args_custom", config)
        self.assertNotIn("guidance_scale", config)
        self.assertNotIn("sigmoid_scale", config)
        self.assertNotIn("discrete_flow_shift", config)
        self.assertEqual(config["qwen3"], "C:/models/qwen3")

    def test_config_sanitize_removes_empty_arg_lists(self):
        config = {
            "network_args": ["dropout=undefined", "empty=", "broken"],
            "optimizer_args_custom": ["eps=null"],
        }

        normalize_custom_args(config)
        sanitize_config(config)

        self.assertNotIn("network_args", config)
        self.assertNotIn("optimizer_args", config)

    def test_fix_config_types_removes_invalid_float_ui_values(self):
        config = {
            "guidance_scale": "undefined",
            "sigmoid_scale": "inf",
            "discrete_flow_shift": "not-a-number",
        }

        fix_config_types(config)

        self.assertNotIn("guidance_scale", config)
        self.assertNotIn("sigmoid_scale", config)
        self.assertNotIn("discrete_flow_shift", config)


if __name__ == "__main__":
    unittest.main()

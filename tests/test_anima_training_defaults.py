import unittest
from unittest import mock

from mikazuki.app.api import apply_anima_training_defaults


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

    def test_anima_lokr_bf16_warns_without_changing_full_precision(self):
        config = {
            "mixed_precision": "bf16",
            "optimizer_type": "AdamW8bit",
            "network_module": "lycoris.kohya",
            "network_args": ["algo=lokr", "factor=8"],
            "unet_lr": "5e-5",
            "attn_mode": "torch",
        }

        apply_anima_training_defaults(config, "anima-lora")

        self.assertNotIn("full_bf16", config)
        self.assertIn("may require full_bf16=true", config["_training_warnings"][0])

    def test_anima_lokr_full_matrix_warns_without_changing_user_params(self):
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

        self.assertTrue(config["full_bf16"])
        self.assertNotIn("scale_weight_norms", config)
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

        with mock.patch("mikazuki.app.train_submit._cuda_bf16_supported", return_value=True):
            apply_anima_training_defaults(config, "anima-lora")

        self.assertEqual(config["mixed_precision"], "bf16")
        self.assertNotIn("full_fp16", config)
        self.assertNotIn("scale_weight_norms", config)
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

        with mock.patch("mikazuki.app.train_submit._cuda_bf16_supported", return_value=True):
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

        with mock.patch("mikazuki.app.train_submit._cuda_bf16_supported", return_value=False):
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


if __name__ == "__main__":
    unittest.main()

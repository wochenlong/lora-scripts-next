import unittest

from mikazuki.anima_backend.adapter import adapt_anima_config


class AnimaBackendAdapterTests(unittest.TestCase):
    def test_adapter_keeps_supported_anima_fields(self):
        config = {
            "model_train_type": "anima-lora",
            "pretrained_model_name_or_path": "./sd-models/anima/anima-preview3-base.safetensors",
            "vae": "./sd-models/anima/qwen_image_vae.safetensors",
            "qwen3": "./sd-models/anima/qwen_3_06b_base.safetensors",
            "network_module": "networks.lora_anima",
            "network_dim": 16,
            "network_alpha": 16,
            "enable_preview": True,
            "sample_width": 1024,
            "sample_height": 1024,
        }

        adapted, warnings = adapt_anima_config(config)

        self.assertTrue(adapted["pretrained_model_name_or_path"].endswith("anima-preview3-base.safetensors"))
        self.assertTrue(adapted["vae"].endswith("qwen_image_vae.safetensors"))
        self.assertTrue(adapted["qwen3"].endswith("qwen_3_06b_base.safetensors"))
        self.assertEqual(adapted["network_module"], "networks.lora_anima")
        self.assertEqual(adapted["network_dim"], 16)
        self.assertNotIn("model_train_type", adapted)
        self.assertNotIn("enable_preview", adapted)
        self.assertEqual(warnings, [])

    def test_adapter_warns_for_unsupported_debug_fields(self):
        adapted, warnings = adapt_anima_config(
            {
                "pretrained_model_name_or_path": "model.safetensors",
                "anima_debug_mode": True,
                "anima_rope_mismatch_mode": "resample",
            }
        )

        self.assertEqual(adapted["pretrained_model_name_or_path"], "model.safetensors")
        self.assertNotIn("anima_debug_mode", adapted)
        self.assertNotIn("anima_rope_mismatch_mode", adapted)
        self.assertIn("Unsupported Anima field ignored: anima_debug_mode", warnings)
        self.assertIn("Unsupported Anima field ignored: anima_rope_mismatch_mode", warnings)

    def test_network_args_custom_becomes_network_args(self):
        adapted, warnings = adapt_anima_config(
            {
                "network_args_custom": ["train_llm_adapter=True", "verbose=True"],
            }
        )

        self.assertEqual(adapted["network_args"], ["train_llm_adapter=True", "verbose=True"])
        self.assertNotIn("network_args_custom", adapted)
        self.assertEqual(warnings, [])

    def test_adapter_warns_when_unknown_field_is_passed_through(self):
        adapted, warnings = adapt_anima_config({"future_sd_scripts_option": "enabled"})

        self.assertEqual(adapted["future_sd_scripts_option"], "enabled")
        self.assertIn("Unknown field passed through to sd-scripts: future_sd_scripts_option", warnings)

    def test_tlora_fields_injected_into_network_args(self):
        config = {
            "network_module": "networks.tlora_anima",
            "network_dim": 16,
            "network_alpha": 16,
            "tlora_min_rank": 2,
            "tlora_rank_schedule": "linear",
            "tlora_orthogonal_init": True,
        }
        adapted, warnings = adapt_anima_config(config)

        self.assertIn("network_args", adapted)
        self.assertIn("tlora_min_rank=2", adapted["network_args"])
        self.assertIn("tlora_rank_schedule=linear", adapted["network_args"])
        self.assertIn("tlora_orthogonal_init=True", adapted["network_args"])
        self.assertNotIn("tlora_min_rank", adapted)
        self.assertNotIn("tlora_rank_schedule", adapted)
        self.assertNotIn("tlora_orthogonal_init", adapted)
        self.assertEqual(warnings, [])

    def test_tlora_fields_merge_with_existing_network_args(self):
        config = {
            "network_module": "networks.tlora_anima",
            "network_args": ["verbose=True"],
            "tlora_min_rank": 4,
        }
        adapted, warnings = adapt_anima_config(config)

        self.assertIn("verbose=True", adapted["network_args"])
        self.assertIn("tlora_min_rank=4", adapted["network_args"])

    def test_non_tlora_module_ignores_tlora_fields(self):
        config = {
            "network_module": "networks.lora_anima",
            "tlora_min_rank": 2,
        }
        adapted, warnings = adapt_anima_config(config)

        self.assertNotIn("tlora_min_rank", adapted)
        self.assertEqual(warnings, [])

    def test_lora_type_is_ui_only(self):
        config = {
            "lora_type": "tlora",
            "network_module": "networks.tlora_anima",
        }
        adapted, warnings = adapt_anima_config(config)

        self.assertNotIn("lora_type", adapted)

    def test_dora_lora_type_maps_to_lycoris_dora_args(self):
        config = {
            "lora_type": "dora",
            "network_dim": 16,
            "network_alpha": 16,
            "network_args": ["algo=lokr", "dora_wd=False"],
            "lokr_factor": 8,
            "full_matrix": True,
            "dropout": 0.1,
        }
        adapted, warnings = adapt_anima_config(config)

        na = adapted["network_args"]
        self.assertEqual(adapted["network_module"], "lycoris.kohya")
        self.assertIn("algo=lora", na)
        self.assertIn("dora_wd=True", na)
        self.assertIn("dropout=0.1", na)
        self.assertTrue(any(item.startswith("preset=") for item in na))
        self.assertNotIn("algo=lokr", na)
        self.assertNotIn("dora_wd=False", na)
        self.assertNotIn("factor=8", na)
        self.assertNotIn("full_matrix=True", na)
        self.assertNotIn("lora_type", adapted)
        self.assertEqual(warnings, [])

    def test_lycoris_fields_injected_into_network_args(self):
        config = {
            "network_module": "lycoris.kohya",
            "network_dim": 16,
            "network_alpha": 16,
            "lycoris_algo": "lokr",
            "lokr_factor": -1,
            "use_cp": True,
            "decompose_both": True,
            "use_scalar": False,
            "dora_wd": True,
            "full_matrix": True,
            "bypass_mode": False,
            "dropout": 0.1,
            "rank_dropout": 0.05,
            "module_dropout": 0.0,
        }
        adapted, warnings = adapt_anima_config(config)

        na = adapted["network_args"]
        self.assertIn("algo=lokr", na)
        self.assertIn("factor=-1", na)
        self.assertIn("use_cp=True", na)
        self.assertIn("decompose_both=True", na)
        self.assertIn("dora_wd=True", na)
        self.assertIn("full_matrix=True", na)
        self.assertIn("dropout=0.1", na)
        self.assertIn("rank_dropout=0.05", na)
        # False values should be omitted (use LyCORIS defaults)
        self.assertNotIn("use_scalar=False", na)
        self.assertNotIn("bypass_mode=False", na)
        # These should NOT appear as top-level keys
        self.assertNotIn("lycoris_algo", adapted)
        self.assertNotIn("lokr_factor", adapted)
        self.assertNotIn("use_cp", adapted)
        self.assertNotIn("full_matrix", adapted)
        self.assertEqual(warnings, [])

    def test_lycoris_preset_and_fields_coexist(self):
        config = {
            "network_module": "lycoris.kohya",
            "lycoris_algo": "lokr",
            "lokr_factor": 16,
            "full_matrix": True,
            "network_args": ["verbose=True"],
        }
        adapted, warnings = adapt_anima_config(config)

        na = adapted["network_args"]
        self.assertIn("verbose=True", na)
        self.assertTrue(any(item.startswith("preset=") for item in na))
        self.assertIn("algo=lokr", na)
        self.assertIn("factor=16", na)
        self.assertIn("full_matrix=True", na)

    def test_non_lycoris_module_ignores_lycoris_fields(self):
        config = {
            "network_module": "networks.lora_anima",
            "use_cp": True,
            "lokr_factor": 8,
            "full_matrix": True,
        }
        adapted, warnings = adapt_anima_config(config)

        self.assertNotIn("use_cp", adapted)
        self.assertNotIn("lokr_factor", adapted)
        self.assertNotIn("full_matrix", adapted)
        self.assertEqual(warnings, [])

    def test_lycoris_zero_numeric_values_passed_through(self):
        """Numeric 0 is a valid value (e.g. dropout=0) and should be included."""
        config = {
            "network_module": "lycoris.kohya",
            "lycoris_algo": "lokr",
            "dropout": 0,
            "module_dropout": 0.0,
        }
        adapted, warnings = adapt_anima_config(config)

        na = adapted["network_args"]
        self.assertIn("dropout=0", na)
        self.assertIn("module_dropout=0.0", na)


if __name__ == "__main__":
    unittest.main()

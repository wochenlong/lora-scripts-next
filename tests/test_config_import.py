import unittest

from mikazuki.utils.config_import import analyze_train_type, infer_train_type, validate_config_import


class ConfigImportTests(unittest.TestCase):
    def test_standard_anima_lokr_on_fast_page_redirects_to_standard_mode(self):
        config = {
            "model_train_type": "anima-lora",
            "lora_type": "lokr",
            "network_module": "lycoris.kohya",
            "qwen3": "qwen_3_06b_base.safetensors",
            "network_args": ["algo=lokr", "factor=-1"],
        }

        result = validate_config_import("anima-lora-fast", config)

        self.assertEqual(result["result"], "redirect")
        self.assertEqual(result["target_path"], "/lora/sd3.html")

    def test_native_anima_fast_config_is_accepted_on_fast_page(self):
        config = {
            "model_train_type": "anima-lora-fast",
            "lora_type": "lora",
            "method": "lora",
            "methods_subdir": "gui-methods",
            "static_token_count": 4096,
            "compile_mode": "blocks",
            "qwen3": "qwen_3_06b_base.safetensors",
        }

        result = validate_config_import("anima-lora-fast", config)

        self.assertEqual(result["result"], "ok")
        self.assertEqual(result["config"]["model_train_type"], "anima-lora-fast")

    def test_native_anima_fast_config_on_standard_page_redirects_to_fast_mode(self):
        config = {
            "model_train_type": "anima-lora-fast",
            "method": "lora",
            "methods_subdir": "gui-methods",
            "static_token_count": 4096,
            "compile_mode": "blocks",
            "qwen3": "qwen_3_06b_base.safetensors",
        }

        result = validate_config_import("sd3-lora", config)

        self.assertEqual(result["result"], "redirect")
        self.assertEqual(result["target_path"], "/lora/anima-fast.html")

    def test_sdxl_on_anima_page_redirects(self):
        config = {
            "model_train_type": "sdxl-lora",
            "pretrained_model_name_or_path": "./sd-models/sdxl/model.safetensors",
            "train_data_dir": "./train/data",
            "max_train_epochs": 10,
        }
        result = validate_config_import("sd3-lora", config)
        self.assertEqual(result["result"], "redirect")
        self.assertEqual(result["target_path"], "/lora/master.html")

    def test_stale_sdxl_type_with_anima_fields_allowed_on_anima_page(self):
        config = {
            "model_train_type": "sdxl-lora",
            "pretrained_model_name_or_path": "anima-base-v1.0.safetensors",
            "qwen3": "qwen_3_06b_base.safetensors",
            "vae": "qwen_image_vae.safetensors",
            "network_module": "lycoris.kohya",
        }
        result = validate_config_import("sd3-lora", config)
        self.assertEqual(result["result"], "ok")
        self.assertEqual(result["config"]["model_train_type"], "anima-lora")
        self.assertIn("notice", result)
        self.assertIn("sdxl-lora", result["notice"])
        self.assertIn("anima-lora", result["notice"])
        self.assertTrue(result["detection_reasons"])

    def test_infer_anima_from_model_paths_only(self):
        config = {
            "model_train_type": "sdxl-lora",
            "pretrained_model_name_or_path": "E:/SD-Trainer/sd-models/anima/anima-base-v1.0.safetensors",
            "vae": "E:/SD-Trainer/sd-models/anima/qwen_image_vae.safetensors",
            "qwen3": "E:/SD-Trainer/sd-models/anima/qwen_3_06b_base.safetensors",
        }
        analysis = analyze_train_type(config)
        self.assertEqual(analysis.train_type, "anima-lora")
        self.assertGreaterEqual(len(analysis.reasons), 3)

    def test_redirect_message_includes_detection_reasons(self):
        config = {
            "model_train_type": "sdxl-lora",
            "pretrained_model_name_or_path": "anima-base-v1.0.safetensors",
            "qwen3": "qwen_3_06b_base.safetensors",
            "vae": "qwen_image_vae.safetensors",
        }
        result = validate_config_import("lora-master", config)
        self.assertEqual(result["result"], "redirect")
        self.assertIn("依据", result["message"])
        self.assertIn("qwen3", result["message"])

    def test_missing_train_type_on_anima_page_gets_default(self):
        config = {
            "pretrained_model_name_or_path": "anima-base-v1.0.safetensors",
            "qwen3": "qwen_3_06b_base.safetensors",
            "vae": "qwen_image_vae.safetensors",
        }
        result = validate_config_import("sd3-lora", config)
        self.assertEqual(result["result"], "ok")
        self.assertEqual(result["config"]["model_train_type"], "anima-lora")

    def test_legacy_sd3_train_type_on_anima_page(self):
        config = {
            "model_train_type": "sd3-lora",
            "qwen3": "qwen_3_06b_base.safetensors",
            "vae": "qwen_image_vae.safetensors",
        }
        result = validate_config_import("sd3-lora", config)
        self.assertEqual(result["result"], "ok")
        self.assertEqual(result["config"]["model_train_type"], "anima-lora")

    def test_sdxl_config_on_master_page_ok(self):
        config = {
            "model_train_type": "sdxl-lora",
            "pretrained_model_name_or_path": "./sd-models/sdxl/model.safetensors",
        }
        result = validate_config_import("lora-master", config)
        self.assertEqual(result["result"], "ok")
        self.assertEqual(result["config"]["model_train_type"], "sdxl-lora")

    def test_anima_config_on_master_page_redirects(self):
        config = {
            "model_train_type": "anima-lora",
            "qwen3": "qwen_3_06b_base.safetensors",
            "vae": "qwen_image_vae.safetensors",
        }
        result = validate_config_import("lora-master", config)
        self.assertEqual(result["result"], "redirect")
        self.assertEqual(result["target_path"], "/lora/sd3.html")

    def test_infer_anima_from_network_module(self):
        config = {"network_module": "networks.lora_anima"}
        self.assertEqual(infer_train_type(config), "anima-lora")

    def test_krea2_export_imported_on_krea2_page_ok(self):
        config = {
            "model_train_type": "krea2-lora",
            "dit": "./sd-models/krea2/krea2.safetensors",
            "vae": "./sd-models/krea2/qwen_image_vae.safetensors",
            "text_encoder": "./sd-models/krea2/qwen3_vl_4b.safetensors",
            "fp8_base": True,
            "fp8_scaled": True,
            "guidance_scale": 1.0,
        }
        result = validate_config_import("krea2-lora", config)
        self.assertEqual(result["result"], "ok")
        self.assertEqual(result["config"]["model_train_type"], "krea2-lora")

    def test_krea2_config_on_anima_page_redirects_to_krea2(self):
        config = {
            "model_train_type": "krea2-lora",
            "dit": "./sd-models/krea2/krea2.safetensors",
            "vae": "./sd-models/krea2/qwen_image_vae.safetensors",
            "text_encoder": "./sd-models/krea2/qwen3_vl_4b.safetensors",
            "fp8_scaled": True,
        }
        result = validate_config_import("sd3-lora", config)
        self.assertEqual(result["result"], "redirect")
        self.assertEqual(result["target_path"], "/lora/krea2.html")

    def test_infer_krea2_from_markers_with_renamed_paths(self):
        config = {
            "model_train_type": "krea2-lora",
            "dit": "./models/base.safetensors",
            "text_encoder": "./models/te.safetensors",
            "fp8_scaled": True,
        }
        analysis = analyze_train_type(config)
        self.assertEqual(analysis.train_type, "krea2-lora")

    def test_reject_non_object_config(self):
        result = validate_config_import("sd3-lora", "not-a-dict")  # type: ignore[arg-type]
        self.assertEqual(result["result"], "reject")

    def test_reject_sd_scripts_intermediate_toml(self):
        config = {
            "network_module": "networks.lora_anima",
            "pretrained_model_name_or_path": "./sd-models/anima/anima-base-v1.0.safetensors",
            "train_data_dir": "./train",
            "max_train_epochs": 2,
        }
        result = validate_config_import("sd3-lora", config)
        self.assertEqual(result["result"], "reject")
        self.assertTrue(any("sd-scripts" in err for err in result["errors"]))

    def test_legacy_preview_fields_add_enable_preview_on_import(self):
        config = {
            "pretrained_model_name_or_path": "./sd-models/anima/anima-base-v1.0.safetensors",
            "vae": "./sd-models/anima/qwen_image_vae.safetensors",
            "qwen3": "./sd-models/anima/qwen_3_06b_base.safetensors",
            "network_module": "networks.lora_anima",
            "sample_at_first": True,
            "sample_every_n_epochs": 2,
            "sample_prompts": "./config/autosave/demo-promopt.txt",
        }
        result = validate_config_import("sd3-lora", config)
        self.assertEqual(result["result"], "ok")
        self.assertTrue(result["config"]["enable_preview"])
        self.assertEqual(result["config"]["sample_every_n_epochs"], 2)

    def test_history_row_wrapper_unwraps_before_import(self):
        inner = {
            "model_train_type": "anima-lora",
            "pretrained_model_name_or_path": "./sd-models/anima/anima-base-v1.0.safetensors",
            "positive_prompts": "1girl",
            "sample_at_first": True,
        }
        wrapper = {"time": "2026-06-27", "name": "demo", "value": inner}
        result = validate_config_import("sd3-lora", wrapper)
        self.assertEqual(result["result"], "ok")
        self.assertEqual(result["config"]["model_train_type"], "anima-lora")
        self.assertNotIn("time", result["config"])
        self.assertNotIn("value", result["config"])
        self.assertTrue(result["config"]["enable_preview"])

    def test_cannot_import_toml_lokr_preview_signals(self):
        import toml

        cfg = toml.loads(
            """
model_train_type = "anima-lora"
lora_type = "lokr"
network_module = "lycoris.kohya"
positive_prompts = "portrait"
network_args = [
  "conv_dim=16",
  "conv_alpha=1",
  "dropout=0",
  "algo=lokr",
  "factor=-1"
]
optimizer_args = ["decouple=True", "weight_deca"]
"""
        )
        result = validate_config_import("sd3-lora", cfg)
        self.assertEqual(result["result"], "ok")
        self.assertTrue(result["config"]["enable_preview"])
        self.assertEqual(result["config"]["lora_type"], "lokr")
        self.assertEqual(result["config"]["conv_dim"], 16)
        self.assertEqual(result["config"]["conv_alpha"], 1)
        self.assertEqual(result["config"]["dropout"], 0)
        self.assertEqual(result["config"]["lycoris_algo"], "lokr")
        self.assertEqual(result["config"]["lokr_factor"], -1)
        self.assertNotIn("weight_deca", result["config"].get("optimizer_args", []))

    def test_lokr627_poisoned_undefined_network_args_sanitized(self):
        config = {
            "model_train_type": "anima-lora",
            "network_module": "lycoris.kohya",
            "network_args": [
                "algo=lokr",
                "conv_dim=undefined",
                "conv_alpha=undefined",
                "dropout=undefined",
                "factor=-1",
            ],
        }
        result = validate_config_import("sd3-lora", config)
        self.assertEqual(result["result"], "ok")
        args = result["config"].get("network_args") or []
        self.assertIn("algo=lokr", args)
        self.assertIn("factor=-1", args)
        self.assertFalse(any("undefined" in item for item in args))
        self.assertEqual(result["config"]["lycoris_algo"], "lokr")
        self.assertEqual(result["config"]["lokr_factor"], -1)


if __name__ == "__main__":
    unittest.main()

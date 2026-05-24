import unittest

from mikazuki.utils.config_import import infer_train_type, validate_config_import


class ConfigImportTests(unittest.TestCase):
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

    def test_reject_non_object_config(self):
        result = validate_config_import("sd3-lora", "not-a-dict")  # type: ignore[arg-type]
        self.assertEqual(result["result"], "reject")


if __name__ == "__main__":
    unittest.main()

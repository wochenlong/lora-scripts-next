import unittest

from mikazuki.anima_backend.adapter import adapt_anima_config


class AnimaFinetuneAdapterTests(unittest.TestCase):
    def test_strips_network_fields_for_finetune(self):
        config = {
            "model_train_type": "anima-finetune",
            "pretrained_model_name_or_path": "dit.safetensors",
            "vae": "vae.safetensors",
            "qwen3": "qwen3.safetensors",
            "learning_rate": "1e-5",
            "network_module": "networks.lora_anima",
            "network_dim": 16,
            "enable_preview": True,
        }

        adapted, warnings = adapt_anima_config(config, finetune=True)

        self.assertIn("pretrained_model_name_or_path", adapted)
        self.assertIn("learning_rate", adapted)
        self.assertNotIn("network_module", adapted)
        self.assertNotIn("network_dim", adapted)
        self.assertNotIn("model_train_type", adapted)
        self.assertNotIn("enable_preview", adapted)


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import patch

from mikazuki.utils import train_utils


class TrainUtilsModelValidationTests(unittest.TestCase):
    def test_unknown_checkpoint_message_does_not_advertise_lumina_frontend(self):
        with (
            patch("mikazuki.utils.train_utils.os.path.exists", return_value=True),
            patch("mikazuki.utils.train_utils.os.path.isdir", return_value=False),
            patch("mikazuki.utils.train_utils.guess_model_type", return_value=train_utils.ModelType.UNKNOWN),
        ):
            valid, message = train_utils.validate_model("unknown.safetensors", "sd-lora")

        self.assertFalse(valid)
        self.assertIn("底模与当前训练入口不匹配", message)
        self.assertNotIn("Flux or Lumina", message)
        self.assertNotIn("Flux 或 Lumina", message)


if __name__ == "__main__":
    unittest.main()

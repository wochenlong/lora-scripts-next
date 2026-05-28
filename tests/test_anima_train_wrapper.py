import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def load_wrapper_module():
    script = Path("scripts/dev/anima_train_network.py").resolve()
    spec = importlib.util.spec_from_file_location("anima_train_network_wrapper", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class AnimaTrainWrapperTests(unittest.TestCase):
    def test_rewrite_config_file_writes_adapted_config(self):
        module = load_wrapper_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "anima.toml"
            config_path.write_text(
                '\n'.join(
                    [
                        'model_train_type = "anima-lora"',
                        'pretrained_model_name_or_path = "model.safetensors"',
                        'vae = "vae.safetensors"',
                        'qwen3 = "qwen3.safetensors"',
                        'network_module = "networks.lora_anima"',
                        'enable_preview = true',
                    ]
                ),
                encoding="utf-8",
            )
            argv = ["anima_train_network.py", "--config_file", str(config_path)]

            adapted_path = module._rewrite_config_file(argv)

            self.assertIsNotNone(adapted_path)
            assert adapted_path is not None
            self.assertEqual(argv[-1], str(adapted_path))
            adapted_text = adapted_path.read_text(encoding="utf-8")
            self.assertIn('pretrained_model_name_or_path = "model.safetensors"', adapted_text)
            self.assertNotIn("model_train_type", adapted_text)
            self.assertNotIn("enable_preview", adapted_text)

    def test_rewrite_config_file_ignores_missing_config_arg(self):
        module = load_wrapper_module()

        self.assertIsNone(module._rewrite_config_file(["anima_train_network.py"]))

    def test_wrapper_script_launch_shape_can_import_local_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "anima.toml"
            config_path.write_text(
                '\n'.join(
                    [
                        'pretrained_model_name_or_path = "model.safetensors"',
                        'vae = "vae.safetensors"',
                        'qwen3 = "qwen3.safetensors"',
                    ]
                ),
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["ANIMA_BACKEND_WRAPPER_SMOKE"] = "1"
            result = subprocess.run(
                [sys.executable, "scripts/dev/anima_train_network.py", "--config_file", str(config_path)],
                cwd=Path.cwd(),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Anima backend wrapper smoke OK", result.stdout)

    def test_finetune_wrapper_smoke(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "anima-finetune.toml"
            config_path.write_text(
                "\n".join(
                    [
                        'pretrained_model_name_or_path = "model.safetensors"',
                        'vae = "vae.safetensors"',
                        'qwen3 = "qwen3.safetensors"',
                        'learning_rate = "1e-5"',
                    ]
                ),
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["ANIMA_BACKEND_WRAPPER_SMOKE"] = "1"
            result = subprocess.run(
                [sys.executable, "scripts/dev/anima_train.py", "--config_file", str(config_path)],
                cwd=Path.cwd(),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("anima_train.py", result.stdout)


if __name__ == "__main__":
    unittest.main()

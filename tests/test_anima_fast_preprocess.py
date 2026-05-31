from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mikazuki.anima_fast_backend.preprocess import (
    ensure_output_directories,
    prepare_anima_fast_dataset,
    user_left_resized_empty,
)
from mikazuki.anima_fast_backend.settings import RuntimeConfig


def make_runtime(root: Path) -> RuntimeConfig:
    anima = root / "extensions" / "anima_lora" / "source"
    anima.mkdir(parents=True)
    (anima / "train.py").write_text("print('train')", encoding="utf-8")
    (anima / "configs").mkdir()
    (anima / "configs" / "base.toml").write_text("", encoding="utf-8")
    (anima / "preprocess").mkdir()
    (anima / "preprocess" / "resize_images.py").write_text("print('resize')", encoding="utf-8")
    python = root / "extensions" / "anima_lora" / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    return RuntimeConfig(
        anima_root=anima,
        python=python,
        lora_next_root=root,
        output_dir=root / "output" / "anima_fast",
        logging_dir=root / "logs" / "anima_fast",
        cache_dir=root / ".cache" / "anima_fast",
    )


class AnimaFastPreprocessTests(unittest.TestCase):
    def test_user_left_resized_empty(self):
        self.assertTrue(user_left_resized_empty({"train_data_dir": "./data/x"}))
        self.assertFalse(user_left_resized_empty({"resized_image_dir": "./cache/resized"}))

    def test_ensure_output_directories_creates_paths(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            values = {
                "output_dir": str(root / "output" / "run"),
                "logging_dir": str(root / "logs" / "run"),
                "lora_cache_dir": str(root / ".cache" / "lora"),
                "resized_image_dir": str(root / ".cache" / "resized"),
            }
            created = ensure_output_directories(values)
            self.assertEqual(len(created), 4)
            for path in created:
                self.assertTrue(Path(path).is_dir())

    def test_prepare_auto_resize_when_resized_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            dataset = root / "data" / "demo" / "10_style"
            dataset.mkdir(parents=True)
            (dataset / "1.png").write_bytes(b"png")
            (dataset / "1.txt").write_text("tag", encoding="utf-8")

            config = {
                "train_data_dir": "./data/demo",
                "pretrained_model_name_or_path": "./sd-models/anima/anima-base-v1.0.safetensors",
                "vae": "./sd-models/anima/qwen_image_vae.safetensors",
                "qwen3": "./sd-models/anima/qwen_3_06b_base.safetensors",
                "resolution": "512,512",
            }

            with mock.patch("mikazuki.anima_fast_backend.preprocess.run_resize_images") as resize:
                result = prepare_anima_fast_dataset(config, runtime, "20260101-test")
                resize.assert_called_once()
                self.assertTrue(result.auto_resized)
                resized = Path(result.adapted.values["resized_image_dir"])
                self.assertTrue(resized.is_dir())
                self.assertEqual(
                    resized,
                    (root / ".cache" / "anima_fast" / "data_demo" / "resized").resolve(),
                )
                self.assertNotIn("20260101-test", resized.as_posix())

    def test_prepare_skips_resize_when_resized_provided(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            resized = root / "cache" / "resized" / "10_style"
            resized.mkdir(parents=True)
            (resized / "1.png").write_bytes(b"png")

            config = {
                "train_data_dir": "./data/demo",
                "resized_image_dir": str(resized),
                "pretrained_model_name_or_path": "./sd-models/anima/anima-base-v1.0.safetensors",
                "vae": "./sd-models/anima/qwen_image_vae.safetensors",
                "qwen3": "./sd-models/anima/qwen_3_06b_base.safetensors",
            }

            with mock.patch("mikazuki.anima_fast_backend.preprocess.run_resize_images") as resize:
                result = prepare_anima_fast_dataset(config, runtime, "20260101-test")
                resize.assert_not_called()
                self.assertFalse(result.auto_resized)

    def test_prepare_reuses_existing_stable_resized_cache(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            resized = root / ".cache" / "anima_fast" / "data_demo" / "resized" / "10_style"
            resized.mkdir(parents=True)
            (resized / "1.png").write_bytes(b"png")
            dataset = root / "data" / "demo" / "10_style"
            dataset.mkdir(parents=True)
            (dataset / "2.png").write_bytes(b"png")

            config = {
                "train_data_dir": "./data/demo",
                "pretrained_model_name_or_path": "./sd-models/anima/anima-base-v1.0.safetensors",
                "vae": "./sd-models/anima/qwen_image_vae.safetensors",
                "qwen3": "./sd-models/anima/qwen_3_06b_base.safetensors",
            }

            with mock.patch("mikazuki.anima_fast_backend.preprocess.run_resize_images") as resize:
                result = prepare_anima_fast_dataset(config, runtime, "20260101-test")
                resize.assert_not_called()
                self.assertFalse(result.auto_resized)
                self.assertTrue(any("using existing resized dataset" in w for w in result.warnings))


if __name__ == "__main__":
    unittest.main()

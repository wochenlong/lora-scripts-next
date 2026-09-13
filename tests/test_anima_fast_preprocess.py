from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mikazuki.engines.anima_fast.preprocess import (
    AdapterError,
    ensure_output_directories,
    prepare_anima_fast_dataset,
    user_left_resized_empty,
)
from mikazuki.engines.anima_fast.settings import RuntimeConfig


def make_runtime(root: Path) -> RuntimeConfig:
    anima = root / "extensions" / "anima_lora" / "source"
    anima.mkdir(parents=True)
    (anima / "train.py").write_text("print('train')", encoding="utf-8")
    (anima / "configs").mkdir()
    (anima / "configs" / "base.toml").write_text("", encoding="utf-8")
    (anima / "scripts" / "preprocess").mkdir(parents=True)
    (anima / "scripts" / "preprocess" / "resize_images.py").write_text("print('resize')", encoding="utf-8")
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

            def fake_resize(_runtime, _src, dst, _resolution):
                output = dst / "10_style" / "1.png"
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"png")

            with mock.patch(
                "mikazuki.engines.anima_fast.preprocess.run_resize_images",
                side_effect=fake_resize,
            ) as resize:
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

            with mock.patch("mikazuki.engines.anima_fast.preprocess.run_resize_images") as resize:
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
            (dataset / "1.png").write_bytes(b"png")

            config = {
                "train_data_dir": "./data/demo",
                "pretrained_model_name_or_path": "./sd-models/anima/anima-base-v1.0.safetensors",
                "vae": "./sd-models/anima/qwen_image_vae.safetensors",
                "qwen3": "./sd-models/anima/qwen_3_06b_base.safetensors",
            }

            with mock.patch("mikazuki.engines.anima_fast.preprocess.run_resize_images") as resize:
                result = prepare_anima_fast_dataset(config, runtime, "20260101-test")
                resize.assert_not_called()
                self.assertFalse(result.auto_resized)
                self.assertTrue(any("using existing resized dataset" in w for w in result.warnings))

    def test_prepare_reruns_resize_when_source_grows(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            resized = root / ".cache" / "anima_fast" / "data_demo" / "resized" / "10_style"
            resized.mkdir(parents=True)
            (resized / "a.png").write_bytes(b"png")
            dataset = root / "data" / "demo" / "10_style"
            dataset.mkdir(parents=True)
            for name in ("a.png", "b.png", "c.png"):
                (dataset / name).write_bytes(b"png")

            config = {
                "train_data_dir": "./data/demo",
                "pretrained_model_name_or_path": "./sd-models/anima/anima-base-v1.0.safetensors",
                "vae": "./sd-models/anima/qwen_image_vae.safetensors",
                "qwen3": "./sd-models/anima/qwen_3_06b_base.safetensors",
            }

            def fake_resize(_runtime, _src, dst, _resolution):
                output_dir = dst / "10_style"
                output_dir.mkdir(parents=True, exist_ok=True)
                for name in ("a.png", "b.png", "c.png"):
                    (output_dir / name).write_bytes(b"png")

            with mock.patch(
                "mikazuki.engines.anima_fast.preprocess.run_resize_images",
                side_effect=fake_resize,
            ) as resize:
                result = prepare_anima_fast_dataset(config, runtime, "20260101-test")
                resize.assert_called_once()
                self.assertTrue(result.auto_resized)
                self.assertTrue(any("新增 2 张" in w for w in result.warnings))

    def test_prepare_rejects_source_format_missing_after_resize(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            resized = root / ".cache" / "anima_fast" / "data_demo" / "resized" / "10_style"
            resized.mkdir(parents=True)
            (resized / "a.png").write_bytes(b"png")
            dataset = root / "data" / "demo" / "10_style"
            dataset.mkdir(parents=True)
            (dataset / "a.png").write_bytes(b"png")
            (dataset / "b.tif").write_bytes(b"tiff")

            config = {
                "train_data_dir": "./data/demo",
                "pretrained_model_name_or_path": "./sd-models/anima/anima-base-v1.0.safetensors",
                "vae": "./sd-models/anima/qwen_image_vae.safetensors",
                "qwen3": "./sd-models/anima/qwen_3_06b_base.safetensors",
            }

            with mock.patch("mikazuki.engines.anima_fast.preprocess.run_resize_images"):
                with self.assertRaisesRegex(AdapterError, "resize 后仍缺少"):
                    prepare_anima_fast_dataset(config, runtime, "20260101-test")

    def test_prepare_warns_when_cache_has_removed_images(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            resized = root / ".cache" / "anima_fast" / "data_demo" / "resized" / "10_style"
            resized.mkdir(parents=True)
            for name in ("a.png", "b.png", "old.png"):
                (resized / name).write_bytes(b"png")
            dataset = root / "data" / "demo" / "10_style"
            dataset.mkdir(parents=True)
            for name in ("a.png", "b.png"):
                (dataset / name).write_bytes(b"png")

            config = {
                "train_data_dir": "./data/demo",
                "pretrained_model_name_or_path": "./sd-models/anima/anima-base-v1.0.safetensors",
                "vae": "./sd-models/anima/qwen_image_vae.safetensors",
                "qwen3": "./sd-models/anima/qwen_3_06b_base.safetensors",
            }

            with mock.patch("mikazuki.engines.anima_fast.preprocess.run_resize_images") as resize:
                result = prepare_anima_fast_dataset(config, runtime, "20260101-test")
                resize.assert_not_called()
                self.assertFalse(result.auto_resized)
                self.assertTrue(any("已不在源目录" in w for w in result.warnings))


if __name__ == "__main__":
    unittest.main()

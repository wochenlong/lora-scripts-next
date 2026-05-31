from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mikazuki.anima_fast_backend.adapter import adapt_config, dump_flat_toml
from mikazuki.anima_fast_backend.preview import (
    apply_anima_fast_preview,
    build_sample_prompt_line,
    is_preview_enabled,
)
from mikazuki.anima_fast_backend.settings import RuntimeConfig


def make_runtime(root: Path) -> RuntimeConfig:
    anima = root / "anima"
    anima.mkdir()
    (anima / "train.py").write_text("print('train')", encoding="utf-8")
    (anima / "configs").mkdir()
    (anima / "configs" / "base.toml").write_text("", encoding="utf-8")
    python = anima / ".venv" / "Scripts" / "python.exe"
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


class AnimaFastPreviewTests(unittest.TestCase):
    def test_preview_disabled_strips_sample_fields(self):
        config = {
            "enable_preview": False,
            "sample_prompts": "./prompts.txt",
            "sample_at_first": True,
        }
        warnings = apply_anima_fast_preview(config, "/tmp/autosave", "run-1")
        self.assertEqual(warnings, [])
        self.assertNotIn("sample_prompts", config)

    def test_preview_enabled_writes_prompt_file_and_adapts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            data = root / "data"
            style = data / "1_style"
            style.mkdir(parents=True)
            (style / "a.png").write_bytes(b"png")
            (style / "a.txt").write_text("1girl", encoding="utf-8")

            autosave = root / "config" / "autosave"
            for name in ("model.safetensors", "vae.safetensors", "qwen3.safetensors"):
                (root / name).write_text("", encoding="utf-8")

            config = {
                "enable_preview": True,
                "train_data_dir": str(data),
                "pretrained_model_name_or_path": "./model.safetensors",
                "vae": "./vae.safetensors",
                "qwen3": "./qwen3.safetensors",
                "sample_every_n_epochs": 1,
            }
            run_id = "20260101-test"
            warnings = apply_anima_fast_preview(config, str(autosave), run_id)
            self.assertTrue(any("preview enabled" in item for item in warnings))
            prompt_path = Path(config["sample_prompts"])
            self.assertTrue(prompt_path.is_file())
            self.assertIn("--ss euler", prompt_path.read_text(encoding="utf-8"))

            adapted = adapt_config(config, runtime, run_id)
            self.assertIn("sample_prompts", adapted.values)
            self.assertEqual(adapted.values["sample_every_n_epochs"], 1)
            self.assertTrue(adapted.values["sample_at_first"])
            self.assertNotIn("enable_preview", adapted.values)
            self.assertNotIn("positive_prompts", adapted.values)

    def test_build_sample_prompt_line_uses_anima_defaults(self):
        line = build_sample_prompt_line({})
        self.assertIn("1girl", line)
        self.assertIn("--w 1024", line)
        self.assertIn("--l 4.5", line)
        self.assertIn("--s 40", line)

    def test_preview_enabled_without_enable_preview_flag_when_prompt_fields_present(self):
        config = {
            "sample_every_n_epochs": 2,
            "positive_prompts": "1girl, solo",
        }
        self.assertTrue(is_preview_enabled(config))

    def test_preview_disabled_when_enable_preview_false_even_with_prompt_fields(self):
        config = {
            "enable_preview": False,
            "positive_prompts": "1girl, solo",
            "sample_every_n_epochs": 2,
        }
        self.assertFalse(is_preview_enabled(config))

    def test_orphan_sample_sampler_is_stripped_when_preview_disabled(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            for name in ("model.safetensors", "vae.safetensors", "qwen3.safetensors"):
                (root / name).write_text("", encoding="utf-8")
            config = {
                "enable_preview": False,
                "sample_sampler": "euler",
                "train_data_dir": str(root / "data"),
                "pretrained_model_name_or_path": "./model.safetensors",
                "vae": "./vae.safetensors",
                "qwen3": "./qwen3.safetensors",
            }
            apply_anima_fast_preview(config, str(root / "autosave"), "run-1")
            adapted = adapt_config(config, runtime, "run-1")
            dumped = dump_flat_toml(adapted.values)
            self.assertNotIn("sample_sampler", dumped)
            self.assertNotIn("sample_prompts", dumped)

    def test_frontend_payload_without_enable_preview_still_generates_sample_prompts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            for name in ("model.safetensors", "vae.safetensors", "qwen3.safetensors"):
                (root / name).write_text("", encoding="utf-8")
            config = {
                "positive_prompts": "1girl, solo",
                "negative_prompts": "lowres",
                "sample_every_n_epochs": 1,
                "sample_at_first": True,
                "sample_width": 1024,
                "sample_height": 1024,
                "train_data_dir": str(root / "data"),
                "pretrained_model_name_or_path": "./model.safetensors",
                "vae": "./vae.safetensors",
                "qwen3": "./qwen3.safetensors",
            }
            apply_anima_fast_preview(config, str(root / "autosave"), "run-fe")
            adapted = adapt_config(config, runtime, "run-fe")
            dumped = dump_flat_toml(adapted.values)
            self.assertIn("sample_prompts", dumped)
            self.assertIn("sample_at_first = true", dumped)

    def test_is_preview_enabled_accepts_string_true(self):
        self.assertTrue(is_preview_enabled({"enable_preview": "true"}))
        self.assertFalse(is_preview_enabled({"enable_preview": False}))


if __name__ == "__main__":
    unittest.main()

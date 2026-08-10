from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mikazuki.musubi_backend.adapter import (
    AdapterError,
    NETWORK_MODULE,
    adapt_config,
    build_dataset_config,
    dump_dataset_toml,
    dump_train_toml,
    discover_subsets,
    normalize_kv_args,
    resolution_pair,
)
from mikazuki.musubi_backend.launcher import (
    build_cache_latents_spec,
    build_cache_text_encoder_spec,
    build_train_spec,
)
from mikazuki.musubi_backend.settings import RuntimeConfig


def make_runtime(root: Path) -> RuntimeConfig:
    return RuntimeConfig(
        musubi_root=(root / "vendor" / "musubi-tuner").resolve(),
        python=(root / "vendor" / "musubi-tuner" / ".venv" / "Scripts" / "python.exe").resolve(),
        lora_next_root=root.resolve(),
        output_dir=(root / "output" / "musubi").resolve(),
        logging_dir=(root / "logs" / "musubi").resolve(),
        cache_dir=(root / ".cache" / "musubi").resolve(),
    )


def base_config(root: Path) -> dict:
    return {
        "model_train_type": "krea2-lora",
        "dit": "./sd-models/krea2/krea2.safetensors",
        "vae": "./sd-models/krea2/qwen_image_vae.safetensors",
        "text_encoder": "./sd-models/krea2/qwen3_vl_4b.safetensors",
        "train_data_dir": str(root / "train"),
        "resolution": "1024,1024",
        "train_batch_size": 1,
        "learning_rate": "1e-4",
        "mixed_precision": "bf16",
        "max_train_epochs": 16,
    }


class DatasetConfigTests(unittest.TestCase):
    def test_kohya_repeats_subdirs_become_datasets(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            train = root / "train"
            (train / "10_char").mkdir(parents=True)
            (train / "5_style").mkdir()
            runtime = make_runtime(root)

            dataset = build_dataset_config({"train_data_dir": str(train)}, runtime)

        self.assertEqual(len(dataset["datasets"]), 2)
        repeats = {Path(d["image_directory"]).name: d["num_repeats"] for d in dataset["datasets"]}
        self.assertEqual(repeats, {"10_char": 10, "5_style": 5})
        cache_dirs = [d["cache_directory"] for d in dataset["datasets"]]
        self.assertEqual(len(set(cache_dirs)), 2)

    def test_flat_dir_falls_back_to_single_dataset(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            train = root / "train"
            train.mkdir()
            runtime = make_runtime(root)

            dataset = build_dataset_config({"train_data_dir": str(train)}, runtime)

        self.assertEqual(len(dataset["datasets"]), 1)
        self.assertEqual(dataset["datasets"][0]["num_repeats"], 1)

    def test_missing_data_dir_raises(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            with self.assertRaises(AdapterError):
                build_dataset_config({"train_data_dir": str(Path(td) / "nope")}, runtime)

    def test_dump_dataset_toml_shape(self):
        dataset = {
            "general": {"resolution": [1024, 1024], "caption_extension": ".txt", "batch_size": 1,
                        "enable_bucket": True, "bucket_no_upscale": False},
            "datasets": [{"image_directory": "/data/10_char", "cache_directory": "/cache/10_char", "num_repeats": 10}],
        }
        text = dump_dataset_toml(dataset)
        self.assertIn("[general]", text)
        self.assertIn("resolution = [1024, 1024]", text)
        self.assertIn("[[datasets]]", text)
        self.assertIn('image_directory = "/data/10_char"', text)
        self.assertIn("num_repeats = 10", text)


class AdapterTests(unittest.TestCase):
    def test_basic_mapping_and_type_coercion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "train" / "4_char").mkdir(parents=True)
            runtime = make_runtime(root)
            config = base_config(root)
            config["network_dim"] = "32"
            config["learning_rate"] = "1e-4"
            config["network_args_custom"] = ["exclude_patterns=['.*\\.mlp\\..*']", "bad-line", "k=null"]

            adapted = adapt_config(config, runtime, "run1")

        values = adapted.values
        self.assertEqual(values["network_module"], NETWORK_MODULE)
        self.assertEqual(values["network_dim"], 32)
        self.assertIsInstance(values["network_dim"], int)
        self.assertEqual(values["learning_rate"], 1e-4)
        self.assertIsInstance(values["learning_rate"], float)
        self.assertEqual(values["network_args"], ["exclude_patterns=['.*\\.mlp\\..*']"])
        self.assertTrue(values["dit"].endswith("krea2.safetensors"))
        self.assertNotIn("model_train_type", values)
        self.assertNotIn("train_data_dir", values)

    def test_missing_required_model_field_raises(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "train" / "4_char").mkdir(parents=True)
            runtime = make_runtime(root)
            config = base_config(root)
            del config["text_encoder"]
            with self.assertRaises(AdapterError):
                adapt_config(config, runtime, "run1")

    def test_fp8_base_forces_fp8_scaled(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "train" / "4_char").mkdir(parents=True)
            runtime = make_runtime(root)
            config = base_config(root)
            config["fp8_base"] = True
            config["fp8_scaled"] = False

            adapted = adapt_config(config, runtime, "run1")

        self.assertTrue(adapted.values["fp8_base"])
        self.assertTrue(adapted.values["fp8_scaled"])
        self.assertTrue(any("成对开启" in w or "fp8_scaled" in w for w in adapted.warnings))

    def test_fp8_scaled_alone_forces_fp8_base(self):
        """Regression: only fp8_scaled=true in TOML crashed trainer (fp8_scaled requires fp8_base)."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "train" / "4_char").mkdir(parents=True)
            runtime = make_runtime(root)
            config = base_config(root)
            config.pop("fp8_base", None)
            config["fp8_scaled"] = True

            adapted = adapt_config(config, runtime, "run1")

        self.assertTrue(adapted.values["fp8_base"])
        self.assertTrue(adapted.values["fp8_scaled"])
        self.assertTrue(any("成对开启" in w for w in adapted.warnings))

    def test_fp16_coerced_to_bf16(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "train" / "4_char").mkdir(parents=True)
            runtime = make_runtime(root)
            config = base_config(root)
            config["mixed_precision"] = "fp16"

            adapted = adapt_config(config, runtime, "run1")

        self.assertEqual(adapted.values["mixed_precision"], "bf16")

    def test_turbo_dit_conflicts_with_blocks_to_swap(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "train" / "4_char").mkdir(parents=True)
            runtime = make_runtime(root)
            config = base_config(root)
            config["turbo_dit"] = "./sd-models/krea2/krea2_turbo.safetensors"
            config["blocks_to_swap"] = 10
            with self.assertRaises(AdapterError):
                adapt_config(config, runtime, "run1")

    def test_turbo_dit_cache_requires_turbo_dit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "train" / "4_char").mkdir(parents=True)
            runtime = make_runtime(root)
            config = base_config(root)
            config["turbo_dit_cache"] = True
            with self.assertRaises(AdapterError):
                adapt_config(config, runtime, "run1")

    def test_unknown_fields_warn_not_fail(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "train" / "4_char").mkdir(parents=True)
            runtime = make_runtime(root)
            config = base_config(root)
            config["some_future_option"] = 123

            adapted = adapt_config(config, runtime, "run1")

        self.assertNotIn("some_future_option", adapted.values)
        self.assertTrue(any("some_future_option" in w for w in adapted.warnings))

    def test_dump_train_toml(self):
        text = dump_train_toml({"network_dim": 32, "mixed_precision": "bf16", "fp8_base": True,
                                "network_args": ["exclude_patterns=['a']"]})
        self.assertIn("network_dim = 32", text)
        self.assertIn('mixed_precision = "bf16"', text)
        self.assertIn("fp8_base = true", text)
        self.assertIn("network_args = [\"exclude_patterns=['a']\"]", text)


class LauncherTests(unittest.TestCase):
    def test_specs_point_at_venv_and_src_on_pythonpath(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            dataset_toml = root / "d.toml"
            train_toml = root / "t.toml"

            latents = build_cache_latents_spec(runtime, dataset_toml, "/models/vae.safetensors", "task-cache_latents", ["0"])
            te = build_cache_text_encoder_spec(runtime, dataset_toml, "/models/te.safetensors", "task-cache_text_encoder")
            train = build_train_spec(runtime, train_toml, "task")

        for spec in (latents, te, train):
            self.assertEqual(spec.command[0], str(runtime.python))
            self.assertEqual(spec.cwd, runtime.musubi_root)
            self.assertEqual(spec.env["PYTHONNOUSERSITE"], "1")
            self.assertIn(str((runtime.musubi_root / "src").resolve()), spec.env["PYTHONPATH"].split(";"))

        self.assertIn("krea2_cache_latents.py", latents.command[1])
        self.assertIn("--skip_existing", latents.command)
        self.assertIn("--vae", latents.command)
        self.assertIn("krea2_cache_text_encoder_outputs.py", te.command[1])
        self.assertIn("--text_encoder", te.command)
        self.assertIn("krea2_train_network.py", train.command[1])
        self.assertEqual(train.command[-1], str(train_toml))
        self.assertEqual(latents.env["CUDA_VISIBLE_DEVICES"], "0")
        self.assertEqual(latents.env["MUSUBI_PARENT_TASK_ID"], "task-cache_latents")


class HelperTests(unittest.TestCase):
    def test_resolution_pair(self):
        self.assertEqual(resolution_pair("1024,1024"), [1024, 1024])
        self.assertEqual(resolution_pair("960x544"), [960, 544])
        self.assertEqual(resolution_pair(768), [768, 768])
        self.assertEqual(resolution_pair(None), [1024, 1024])

    def test_normalize_kv_args_dedup_last_wins(self):
        self.assertEqual(normalize_kv_args(["a=1", "b=2", "a=3"]), ["a=3", "b=2"])

    def test_discover_subsets_ignores_non_repeat_dirs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "10_ok").mkdir()
            (root / "random").mkdir()
            entries = discover_subsets(root)
        self.assertEqual(entries, [(root / "10_ok", 10)])


if __name__ == "__main__":
    unittest.main()

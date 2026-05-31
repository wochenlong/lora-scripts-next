from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from mikazuki.anima_fast_backend.adapter import (
    AdapterError,
    adapt_config,
    dataset_cache_slug,
    dump_flat_toml,
)
from mikazuki.anima_fast_backend.extension_state import (
    STATE_INSTALLED_UNVERIFIED,
    STATE_NOT_INSTALLED,
    STATE_READY,
    ExtensionLayout,
    read_extension_status,
    write_install_state,
)
from mikazuki.anima_fast_backend.installer import build_install_plan, copy_source_snapshot, remove_extension
from mikazuki.anima_fast_backend.launcher import build_launch_spec
from mikazuki.anima_fast_backend.preflight import ProbeFacts, run_preflight
from mikazuki.anima_fast_backend.service_resolver import LegacyServiceResolverShim, RegistryServiceResolver
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


class ServiceResolverTests(unittest.TestCase):
    def test_legacy_resolver_does_not_expose_monitor_port(self):
        resolver = LegacyServiceResolverShim({"MIKAZUKI_HOST": "0.0.0.0", "MIKAZUKI_PORT": "28000", "TRAIN_MONITOR_PORT": "6008"})

        self.assertEqual(resolver.public_base_url(), "http://127.0.0.1:28000")
        self.assertEqual(resolver.train_monitor().public_path, "/monitor/")
        self.assertNotIn("6008", resolver.train_monitor().public_url)

    def test_registry_resolver_reads_services_json(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "services.json"
            path.write_text(json.dumps({
                "public_base_url": "http://127.0.0.1:28000",
                "services": {
                    "api": {"public_path": "/api/", "public_url": "http://127.0.0.1:28000/api/"},
                    "train-monitor": {"public_path": "/monitor/", "public_url": "http://127.0.0.1:28000/monitor/"},
                    "tensorboard": {"public_path": "/tensorboard/", "public_url": "http://127.0.0.1:28000/tensorboard/"},
                },
            }), encoding="utf-8")

            resolver = RegistryServiceResolver(path)

        self.assertEqual(resolver.tensorboard().public_path, "/tensorboard/")


class ExtensionStateTests(unittest.TestCase):
    def test_status_transitions(self):
        with tempfile.TemporaryDirectory() as td:
            layout = ExtensionLayout(Path(td) / "anima_lora")

            self.assertEqual(read_extension_status(layout).state, STATE_NOT_INSTALLED)
            layout.source.mkdir(parents=True)
            layout.train_py.write_text("", encoding="utf-8")
            self.assertEqual(read_extension_status(layout).state, STATE_INSTALLED_UNVERIFIED)
            layout.venv_python.parent.mkdir(parents=True)
            layout.venv_python.write_text("", encoding="utf-8")
            write_install_state(layout, STATE_READY, {"audit": {"ok": True}, "torch": "ok"})

            status = read_extension_status(layout)

        self.assertEqual(status.state, STATE_READY)
        self.assertEqual(status.facts["torch"], "ok")


class InstallerTests(unittest.TestCase):
    def test_copy_source_snapshot_includes_expected_runtime_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source_repo"
            source.mkdir()
            (source / "train.py").write_text("print('train')", encoding="utf-8")
            (source / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
            (source / "library").mkdir()
            (source / "library" / "module.py").write_text("", encoding="utf-8")
            (source / "output").mkdir()
            (source / "output" / "ignore.txt").write_text("", encoding="utf-8")
            layout = ExtensionLayout(root / "extensions" / "anima_lora")
            plan = build_install_plan(source, layout, dry_run=False)

            copy_source_snapshot(plan)

            self.assertTrue((layout.source / "train.py").is_file())
            self.assertTrue((layout.source / "library" / "module.py").is_file())
            self.assertFalse((layout.source / "output").exists())

    def test_copy_source_snapshot_can_pin_git_commit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source_repo"
            source.mkdir()
            subprocess.run(["git", "-C", str(source), "init"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(source), "config", "user.email", "test@example.local"], check=True)
            subprocess.run(["git", "-C", str(source), "config", "user.name", "Test"], check=True)
            (source / "train.py").write_text("print('old')\n", encoding="utf-8")
            (source / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
            (source / "library").mkdir()
            (source / "library" / "module.py").write_text("VALUE = 'old'\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(source), "add", "."], check=True)
            subprocess.run(["git", "-C", str(source), "commit", "-m", "old"], check=True, capture_output=True)
            old_commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()

            (source / "train.py").write_text("print('new')\n", encoding="utf-8")
            (source / "library" / "module.py").write_text("VALUE = 'new'\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(source), "add", "."], check=True)
            subprocess.run(["git", "-C", str(source), "commit", "-m", "new"], check=True, capture_output=True)

            layout = ExtensionLayout(root / "extensions" / "anima_lora")
            plan = build_install_plan(source, layout, dry_run=False, source_commit=old_commit)
            copy_source_snapshot(plan)

            self.assertIn("old", (layout.source / "train.py").read_text(encoding="utf-8"))
            self.assertIn(old_commit, (layout.source / ".source_commit").read_text(encoding="utf-8"))

    def test_remove_extension_is_limited_to_extensions_dir(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            layout = ExtensionLayout(root / "extensions" / "anima_lora")
            layout.source.mkdir(parents=True)

            remove_extension(layout, root)

            self.assertFalse(layout.root.exists())
            with self.assertRaises(ValueError):
                remove_extension(ExtensionLayout(root / "outside"), root)


class AdapterTests(unittest.TestCase):
    def test_adapt_config_maps_anima_paths(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            adapted = adapt_config({
                "model_train_type": "anima-lora-fast",
                "lora_type": "lora",
                "train_data_dir": "dataset",
                "pretrained_model_name_or_path": "models/model.safetensors",
                "network_args_custom": ["rank=16"],
            }, runtime, "run-1")

        self.assertEqual(adapted.values["method"], "lora")
        self.assertIn("source_image_dir", adapted.values)
        self.assertIn("resized_image_dir", adapted.values)
        self.assertIn("lora_cache_dir", adapted.values)
        self.assertNotIn("cache_dir", adapted.values)
        self.assertNotIn("model_train_type", adapted.values)
        self.assertIn('method = "lora"', dump_flat_toml(adapted.values))

    def test_adapt_config_uses_stable_dataset_cache_paths(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            adapted = adapt_config(
                {
                    "lora_type": "lora",
                    "train_data_dir": "data/train_data",
                },
                runtime,
                "20260101-run",
            )

        resized = Path(adapted.values["resized_image_dir"])
        lora_cache = Path(adapted.values["lora_cache_dir"])
        self.assertEqual(resized, (root / ".cache" / "anima_fast" / "data_train_data" / "resized").resolve())
        self.assertEqual(lora_cache, (root / ".cache" / "anima_fast" / "data_train_data" / "lora").resolve())
        self.assertNotIn("20260101-run", resized.as_posix())

    def test_dataset_cache_slug_from_relative_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            slug = dataset_cache_slug(root / "data" / "train_data", root)
        self.assertEqual(slug, "data_train_data")

    def test_adapt_config_warns_when_epochs_override_steps(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            adapted = adapt_config({
                "lora_type": "lora",
                "max_train_epochs": 1,
                "max_train_steps": 1,
            }, runtime, "run-1")

        self.assertTrue(any("max_train_epochs is set" in warning for warning in adapted.warnings))

    def test_rejects_non_mvp_lora_type(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            with self.assertRaises(AdapterError):
                adapt_config({"lora_type": "tlora"}, runtime, "run-1")


class PreflightLauncherTests(unittest.TestCase):
    def test_preflight_happy_path_with_injected_probe(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            for file in ("model.safetensors", "vae.safetensors", "qwen.safetensors"):
                (root / file).write_text("", encoding="utf-8")
            dataset = root / "dataset"
            dataset.mkdir()
            (dataset / "a.png").write_text("", encoding="utf-8")
            (dataset / "a.txt").write_text("caption", encoding="utf-8")

            result = run_preflight({
                "pretrained_model_name_or_path": "model.safetensors",
                "vae": "vae.safetensors",
                "qwen3": "qwen.safetensors",
                "train_data_dir": "dataset",
                "resolution": "64,64",
                "static_token_count": 4096,
                "attn_mode": "flash",
            }, runtime, lambda _runtime: ProbeFacts("3.13.11", torch_metadata_version="2.11.0+cu130", cuda_available=True, flash_attn_importable=True))

        self.assertTrue(result.ok, result.errors)

    def test_preflight_warns_for_bucket_static_token_count(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            for file in ("model.safetensors", "vae.safetensors", "qwen.safetensors"):
                (root / file).write_text("", encoding="utf-8")
            dataset = root / "dataset"
            dataset.mkdir()
            (dataset / "a.png").write_text("", encoding="utf-8")
            (dataset / "a.txt").write_text("caption", encoding="utf-8")

            result = run_preflight({
                "pretrained_model_name_or_path": "model.safetensors",
                "vae": "vae.safetensors",
                "qwen3": "qwen.safetensors",
                "train_data_dir": "dataset",
                "resolution": "64,64",
                "static_token_count": 1024,
                "enable_bucket": True,
                "torch_compile": False,
                "attn_mode": "flash",
            }, runtime, lambda _runtime: ProbeFacts("3.13.11", torch_metadata_version="2.11.0+cu130", cuda_available=True, flash_attn_importable=True))

        self.assertTrue(result.ok, result.errors)
        self.assertTrue(any("static_token_count=4096" in warning for warning in result.warnings))

    def test_preflight_rejects_cache_flags_without_preprocess_cache(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            for file in ("model.safetensors", "vae.safetensors", "qwen.safetensors"):
                (root / file).write_text("", encoding="utf-8")
            dataset = root / "dataset"
            dataset.mkdir()
            (dataset / "a.png").write_text("", encoding="utf-8")
            (dataset / "a.txt").write_text("caption", encoding="utf-8")

            result = run_preflight({
                "pretrained_model_name_or_path": "model.safetensors",
                "vae": "vae.safetensors",
                "qwen3": "qwen.safetensors",
                "train_data_dir": "dataset",
                "source_image_dir": "dataset",
                "resized_image_dir": "empty-resized",
                "lora_cache_dir": "empty-lora-cache",
                "resolution": "64,64",
                "static_token_count": 4096,
                "attn_mode": "flash",
                "cache_latents": True,
                "cache_text_encoder_outputs": True,
            }, runtime, lambda _runtime: ProbeFacts("3.13.11", torch_metadata_version="2.11.0+cu130", cuda_available=True, flash_attn_importable=True))

        self.assertFalse(result.ok)
        self.assertTrue(any("cache_latents=true requires completed" in error for error in result.errors))
        self.assertTrue(any("cache_text_encoder_outputs=true requires completed" in error for error in result.errors))

    def test_preflight_allows_live_encoding_without_preprocess_cache(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            for file in ("model.safetensors", "vae.safetensors", "qwen.safetensors"):
                (root / file).write_text("", encoding="utf-8")
            dataset = root / "dataset"
            dataset.mkdir()
            (dataset / "a.png").write_text("", encoding="utf-8")
            (dataset / "a.txt").write_text("caption", encoding="utf-8")

            result = run_preflight({
                "pretrained_model_name_or_path": "model.safetensors",
                "vae": "vae.safetensors",
                "qwen3": "qwen.safetensors",
                "train_data_dir": "dataset",
                "source_image_dir": "dataset",
                "resized_image_dir": "empty-resized",
                "lora_cache_dir": "empty-lora-cache",
                "resolution": "64,64",
                "static_token_count": 4096,
                "attn_mode": "flash",
                "cache_latents": False,
                "cache_text_encoder_outputs": False,
            }, runtime, lambda _runtime: ProbeFacts("3.13.11", torch_metadata_version="2.11.0+cu130", cuda_available=True, flash_attn_importable=True))

        self.assertTrue(result.ok, result.errors)

    def test_preflight_rejects_missing_torch_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            (root / "data").mkdir()
            (root / "data" / "1.png").write_bytes(b"png")
            (root / "data" / "1.txt").write_text("test", encoding="utf-8")
            for name in ("dit.safetensors", "vae.safetensors", "qwen.safetensors"):
                (root / name).write_bytes(b"x")

            result = run_preflight({
                "pretrained_model_name_or_path": str(root / "dit.safetensors"),
                "vae": str(root / "vae.safetensors"),
                "qwen3": str(root / "qwen.safetensors"),
                "train_data_dir": str(root / "data"),
                "torch_compile": False,
                "static_token_count": 4096,
                "attn_mode": "torch",
            }, runtime, lambda _runtime: ProbeFacts("3.13.11", torch_version="2.11.0+cu130", cuda_available=True))

        self.assertFalse(result.ok)
        self.assertTrue(any("torch package metadata is missing" in err for err in result.errors))

    def test_adapt_config_rejects_unsupported_optimizer(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            with self.assertRaises(AdapterError):
                adapt_config(
                    {
                        "model_train_type": "anima-lora-fast",
                        "train_data_dir": str(root / "data"),
                        "optimizer_type": "prodigyplus.ProdigyPlusScheduleFree",
                    },
                    runtime,
                    "run-1",
                )

    def test_adapt_config_accepts_automagic(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            adapted = adapt_config(
                {
                    "model_train_type": "anima-lora-fast",
                    "train_data_dir": str(root / "data"),
                    "optimizer_type": "Automagic",
                    "learning_rate": "1e-6",
                },
                runtime,
                "run-1",
            )
        self.assertEqual(adapted.values["optimizer_type"], "Automagic")
        self.assertTrue(any("Automagic" in w for w in adapted.warnings))

    def test_preflight_rejects_automagic_without_quanto(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            (root / "data").mkdir()
            (root / "data" / "1.png").write_bytes(b"png")
            (root / "data" / "1.txt").write_text("test", encoding="utf-8")
            for name in ("dit.safetensors", "vae.safetensors", "qwen.safetensors"):
                (root / name).write_bytes(b"x")

            result = run_preflight(
                {
                    "pretrained_model_name_or_path": str(root / "dit.safetensors"),
                    "vae": str(root / "vae.safetensors"),
                    "qwen3": str(root / "qwen.safetensors"),
                    "train_data_dir": str(root / "data"),
                    "torch_compile": False,
                    "static_token_count": 4096,
                    "attn_mode": "torch",
                    "optimizer_type": "Automagic",
                },
                runtime,
                lambda _runtime: ProbeFacts(
                    "3.13.11",
                    torch_metadata_version="2.11.0+cu130",
                    cuda_available=True,
                    quanto_importable=False,
                ),
            )

        self.assertFalse(result.ok)
        self.assertTrue(any("Automagic requires optimum-quanto" in err for err in result.errors))

    def test_launcher_uses_external_python_and_isolated_env(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            spec = build_launch_spec(runtime, Path(td) / "config.toml", "task-1", ["0"])

        self.assertEqual(spec.command[0], str(runtime.python))
        self.assertEqual(spec.cwd, runtime.anima_root)
        self.assertEqual(spec.env["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(spec.env["PYTHONNOUSERSITE"], "1")
        self.assertNotIn("PYTHONPATH", spec.env)
        self.assertEqual(spec.env["CUDA_VISIBLE_DEVICES"], "0")


if __name__ == "__main__":
    unittest.main()

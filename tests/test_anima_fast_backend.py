from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from mikazuki.anima_fast_backend import preflight as preflight_module
from mikazuki.anima_fast_backend.adapter import (
    AdapterError,
    adapt_config,
    dataset_cache_slug,
    dump_flat_toml,
    dump_fast_dataset_toml,
    ensure_fast_run_log_dirs,
)
from mikazuki.anima_fast_backend.extension_state import (
    STATE_BROKEN,
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
    def _make_ready_source(self, layout: ExtensionLayout) -> None:
        layout.source.mkdir(parents=True)
        layout.train_py.write_text("", encoding="utf-8")
        (layout.source / "configs").mkdir()
        (layout.source / "configs" / "base.toml").write_text("", encoding="utf-8")
        (layout.source / "preprocess").mkdir()
        (layout.source / "preprocess" / "resize_images.py").write_text("", encoding="utf-8")

    def test_status_transitions(self):
        with tempfile.TemporaryDirectory() as td:
            layout = ExtensionLayout(Path(td) / "anima_lora")

            self.assertEqual(read_extension_status(layout).state, STATE_NOT_INSTALLED)
            self._make_ready_source(layout)
            self.assertEqual(read_extension_status(layout).state, STATE_INSTALLED_UNVERIFIED)
            layout.venv_python.parent.mkdir(parents=True)
            layout.venv_python.write_text("", encoding="utf-8")
            write_install_state(layout, STATE_READY, {"audit": {"ok": True}, "torch": "ok"})

            status = read_extension_status(layout)

        self.assertEqual(status.state, STATE_READY)
        self.assertEqual(status.facts["torch"], "ok")

    def test_ready_state_downgrades_when_runtime_files_are_missing(self):
        with tempfile.TemporaryDirectory() as td:
            layout = ExtensionLayout(Path(td) / "anima_lora")
            layout.source.mkdir(parents=True)
            layout.train_py.write_text("", encoding="utf-8")
            layout.venv_python.parent.mkdir(parents=True)
            layout.venv_python.write_text("", encoding="utf-8")
            write_install_state(layout, STATE_READY, {"audit": {"ok": True}})

            status = read_extension_status(layout)

        self.assertEqual(status.state, STATE_BROKEN)
        self.assertIn("configs/base.toml", status.reason)
        self.assertIn("preprocess/resize_images.py", status.reason)


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
                "network_args_custom": ["rank_dropout=0.1"],
            }, runtime, "run-1")

        self.assertEqual(adapted.values["method"], "lora")
        self.assertIn("source_image_dir", adapted.values)
        self.assertIn("resized_image_dir", adapted.values)
        self.assertIn("lora_cache_dir", adapted.values)
        self.assertNotIn("cache_dir", adapted.values)
        self.assertNotIn("model_train_type", adapted.values)
        self.assertEqual(adapted.values["network_args"], ["rank_dropout=0.1"])
        self.assertIn('method = "lora"', dump_flat_toml(adapted.values))

    def test_fast_variant_defaults_to_lora(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            adapted = adapt_config({}, runtime, "run-1")

        self.assertEqual(adapted.values["method"], "lora")
        self.assertEqual(adapted.values["network_module"], "networks.lora_anima")
        self.assertNotIn("down_init", adapted.values)
        self.assertNotIn("use_timestep_mask=true", adapted.values.get("network_args", []))

    def test_tlora_variant_injects_curated_upstream_flags(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            adapted = adapt_config(
                {
                    "fast_variant": "tlora",
                    "down_init": "gaussian",
                    "network_args_custom": [
                        "rank_dropout=0.1",
                        "use_timestep_mask=false",
                        "min_rank=8",
                        "alpha_rank_scale=0.25",
                    ],
                },
                runtime,
                "run-1",
            )

        self.assertEqual(adapted.values["method"], "lora")
        self.assertEqual(adapted.values["network_module"], "networks.lora_anima")
        self.assertEqual(adapted.values["down_init"], "weight_svd")
        self.assertIn("rank_dropout=0.1", adapted.values["network_args"])
        self.assertIn("use_timestep_mask=true", adapted.values["network_args"])
        self.assertIn("min_rank=1", adapted.values["network_args"])
        self.assertIn("alpha_rank_scale=1.0", adapted.values["network_args"])
        self.assertNotIn("use_timestep_mask=false", adapted.values["network_args"])
        self.assertNotIn("min_rank=8", adapted.values["network_args"])
        self.assertNotIn("alpha_rank_scale=0.25", adapted.values["network_args"])

    def test_unknown_fast_variant_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            with self.assertRaisesRegex(AdapterError, "fast_variant=turbo"):
                adapt_config({"fast_variant": "turbo"}, runtime, "run-1")

    def test_lora_variant_rejects_custom_tlora_network_args(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            with self.assertRaisesRegex(AdapterError, "use_timestep_mask"):
                adapt_config(
                    {
                        "fast_variant": "lora",
                        "network_args_custom": ["use_timestep_mask=true"],
                    },
                    runtime,
                    "run-1",
                )

    def test_lora_variant_ignores_top_level_tlora_bypass_fields(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            adapted = adapt_config(
                {
                    "fast_variant": "lora",
                    "method": "turbo",
                    "use_timestep_mask": True,
                    "min_rank": 8,
                    "alpha_rank_scale": 0.25,
                    "down_init": "weight_svd",
                },
                runtime,
                "run-1",
            )

        self.assertEqual(adapted.values["method"], "lora")
        self.assertNotIn("use_timestep_mask", adapted.values)
        self.assertNotIn("min_rank", adapted.values)
        self.assertNotIn("alpha_rank_scale", adapted.values)
        self.assertNotIn("down_init", adapted.values)

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

    def test_adapt_config_maps_fast_dataset_batch_size_and_repeats(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            adapted = adapt_config(
                {
                    "lora_type": "lora",
                    "train_batch_size": 4,
                    "dataset_repeats": 7,
                },
                runtime,
                "run-1",
            )

        self.assertEqual(adapted.values["train_batch_size"], 4)
        self.assertEqual(adapted.values["batch_size"], 4)
        self.assertEqual(adapted.values["dataset_repeats"], 7)

    def test_dump_fast_dataset_toml_writes_dataset_overrides(self):
        text = dump_fast_dataset_toml(
            {
                "resized_image_dir": "D:/data/resized",
                "lora_cache_dir": "D:/data/lora",
                "caption_extension": ".txt",
                "resolution": "1024,1024",
                "enable_bucket": True,
                "train_batch_size": 4,
                "dataset_repeats": 7,
            }
        )

        self.assertIn("[[datasets]]", text)
        self.assertNotIn("keep_tokens", text)
        self.assertNotIn("resolution =", text)
        self.assertNotIn("enable_bucket", text)
        self.assertNotIn("bucket_reso", text)
        self.assertIn("batch_size = 4", text)
        self.assertIn("[[datasets.subsets]]", text)
        self.assertIn("num_repeats = 7", text)

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

    def test_adapt_config_uses_torch_when_attn_mode_is_empty(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            adapted = adapt_config({
                "lora_type": "lora",
                "attn_mode": "",
            }, runtime, "run-1")

        self.assertEqual(adapted.values["attn_mode"], "torch")
        self.assertTrue(any("attn_mode" in warning for warning in adapted.warnings))

    def test_adapt_config_ignores_v117_removed_fields(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            adapted = adapt_config({
                "lora_type": "lora",
                "resolution": "1536,1536",
                "torch_compile": True,
                "static_token_count": 4096,
                "compile_mode": "full",
                "dynamo_backend": "eager",
            }, runtime, "run-1")

        for field in ("static_token_count", "compile_mode", "dynamo_backend"):
            self.assertNotIn(field, adapted.values)
            self.assertTrue(any(field in warning for warning in adapted.warnings))

    def test_adapt_config_supports_dynamic_compile_and_migrates_legacy_cache_fields(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            adapted = adapt_config(
                {
                    "torch_compile": True,
                    "compile_dynamic_seq": False,
                    "cache_latents": True,
                    "cache_text_encoder_outputs": True,
                },
                runtime,
                "run-1",
            )

        self.assertTrue(adapted.values["compile_dynamic_seq"])
        self.assertTrue(adapted.values["use_vae_cache"])
        self.assertTrue(adapted.values["use_text_cache"])
        self.assertNotIn("cache_latents", adapted.values)
        self.assertNotIn("cache_text_encoder_outputs", adapted.values)
        self.assertTrue(any("compile_dynamic_seq" in warning for warning in adapted.warnings))

    def test_adapt_config_derives_max_bucket_reso_for_high_resolution(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            adapted = adapt_config({
                "lora_type": "lora",
                "resolution": "1536,1536",
                "enable_bucket": True,
            }, runtime, "run-1")

        self.assertEqual(adapted.values["max_bucket_reso"], 1536)
        self.assertTrue(any("max_bucket_reso" in warning for warning in adapted.warnings))
        self.assertNotIn("max_bucket_reso", dump_fast_dataset_toml(adapted.values))

    def test_adapt_config_preserves_valid_user_max_bucket_reso(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            adapted = adapt_config({
                "lora_type": "lora",
                "resolution": "1536,1536",
                "enable_bucket": True,
                "max_bucket_reso": 2048,
            }, runtime, "run-1")

        self.assertEqual(adapted.values["max_bucket_reso"], 2048)
        self.assertFalse(any("max_bucket_reso" in warning for warning in adapted.warnings))

    def test_adapt_config_rejects_max_bucket_reso_below_resolution(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            with self.assertRaisesRegex(
                AdapterError,
                "max_bucket_reso=1024.*resolution=1536,1536",
            ):
                adapt_config({
                    "lora_type": "lora",
                    "resolution": "1536,1536",
                    "enable_bucket": True,
                    "max_bucket_reso": 1024,
                }, runtime, "run-1")

    def test_adapt_config_rounds_max_bucket_reso_to_bucket_step(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            adapted = adapt_config({
                "lora_type": "lora",
                "resolution": "1536,1536",
                "enable_bucket": True,
                "max_bucket_reso": 1550,
                "bucket_reso_steps": 64,
            }, runtime, "run-1")

        self.assertEqual(adapted.values["max_bucket_reso"], 1600)
        self.assertTrue(any("1550" in warning and "1600" in warning for warning in adapted.warnings))

    def test_adapt_config_derives_bucket_limit_when_no_upscale_is_enabled(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            adapted = adapt_config({
                "lora_type": "lora",
                "resolution": "1536,1536",
                "enable_bucket": True,
                "bucket_no_upscale": True,
            }, runtime, "run-1")

        self.assertEqual(adapted.values["max_bucket_reso"], 1536)

    def test_adapt_config_ignores_unsupported_fast_memory_fields(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            adapted = adapt_config({
                "lora_type": "lora",
                "blocks_to_swap": 8,
                "cpu_offload_checkpointing": True,
                "unsloth_offload_checkpointing": True,
            }, runtime, "run-1")

        self.assertNotIn("blocks_to_swap", adapted.values)
        self.assertNotIn("cpu_offload_checkpointing", adapted.values)
        self.assertNotIn("unsloth_offload_checkpointing", adapted.values)
        self.assertTrue(any("blocks_to_swap" in warning for warning in adapted.warnings))

    def test_adapt_config_forces_live_encoding_cache_overrides(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            adapted = adapt_config({
                "lora_type": "lora",
                "cache_latents": False,
                "cache_latents_to_disk": True,
                "cache_text_encoder_outputs": False,
                "cache_text_encoder_outputs_to_disk": True,
            }, runtime, "run-1")

        self.assertFalse(adapted.values["use_vae_cache"])
        self.assertFalse(adapted.values["use_text_cache"])
        toml_text = dump_flat_toml(adapted.values)
        self.assertIn("use_vae_cache = false", toml_text)
        self.assertIn("use_text_cache = false", toml_text)

    def test_adapt_config_uses_short_fast_log_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            adapted = adapt_config({
                "lora_type": "lora",
            }, runtime, "run-1")

        self.assertEqual(adapted.values["log_prefix"], "af_")
        self.assertEqual(adapted.values["log_tracker_name"], "tb")

    def test_ensure_fast_run_log_dirs_creates_tracker_dirs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            values = {
                "logging_dir": str(root / "logs" / "anima_fast"),
                "method": "lora",
                "log_tracker_name": "network_train",
            }

            created = ensure_fast_run_log_dirs(values, now=None)

            self.assertTrue((root / "logs" / "anima_fast").is_dir())
            self.assertGreaterEqual(len(created), 4)
            self.assertTrue(any(path.name == "network_train" for path in created))

    def test_adapt_config_disables_cache_when_skip_cache_check_is_combined(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            adapted = adapt_config({
                "lora_type": "lora",
                "cache_latents": True,
                "cache_text_encoder_outputs": True,
                "skip_cache_check": True,
            }, runtime, "run-1")

        self.assertFalse(adapted.values["use_vae_cache"])
        self.assertFalse(adapted.values["use_text_cache"])
        self.assertFalse(adapted.values["skip_cache_check"])
        self.assertTrue(any("skip_cache_check" in warning for warning in adapted.warnings))

    def test_adapt_config_rejects_unsupported_network_args_custom(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            with self.assertRaisesRegex(AdapterError, "unsupported Anima Fast key"):
                adapt_config({
                    "lora_type": "lora",
                    "network_args_custom": ["train_llm_adapter=True"],
                }, runtime, "run-1")

    def test_adapt_config_rejects_malformed_network_args_custom(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            with self.assertRaisesRegex(AdapterError, "key=value"):
                adapt_config({
                    "lora_type": "lora",
                    "network_args_custom": ["rank_dropout"],
                }, runtime, "run-1")

    def test_rejects_non_mvp_lora_type(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            with self.assertRaises(AdapterError):
                adapt_config({"lora_type": "tlora"}, runtime, "run-1")


class PreflightLauncherTests(unittest.TestCase):
    def test_probe_dit_checkpoint_recognizes_base_and_29b_depth(self):
        import torch
        from safetensors.torch import save_file

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for blocks, variant in ((28, "anima-base"), (40, "anima-2.9b")):
                path = root / f"anima-{blocks}.safetensors"
                tensors = {
                    "net.x_embedder.proj.1.weight": torch.zeros((2048, 1)),
                    **{f"net.blocks.{index}.marker": torch.zeros(1) for index in range(blocks)},
                }
                save_file(tensors, path)

                arch = preflight_module.probe_dit_checkpoint(path)

                self.assertEqual(arch["num_blocks"], blocks)
                self.assertEqual(arch["model_channels"], 2048)
                self.assertEqual(arch["model_variant"], variant)

    def test_preflight_rejects_network_block_metadata_mismatch(self):
        import torch
        from safetensors.torch import save_file

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            model = root / "anima-2.9b.safetensors"
            save_file(
                {
                    "net.x_embedder.proj.1.weight": torch.zeros((2048, 1)),
                    **{f"net.blocks.{index}.marker": torch.zeros(1) for index in range(40)},
                },
                model,
            )
            for name in ("vae.safetensors", "qwen.safetensors"):
                (root / name).write_bytes(b"x")
            dataset = root / "dataset"
            dataset.mkdir()
            (dataset / "a.png").write_bytes(b"png")
            (dataset / "a.txt").write_text("caption", encoding="utf-8")
            network = root / "network_weights.safetensors"
            save_file(
                {"network.weight": torch.zeros(1)},
                network,
                metadata={"ss_num_blocks": "28"},
            )
            result = run_preflight(
                {
                    "pretrained_model_name_or_path": str(model),
                    "vae": str(root / "vae.safetensors"),
                    "qwen3": str(root / "qwen.safetensors"),
                    "train_data_dir": str(dataset),
                    "network_weights": str(network),
                    "torch_compile": False,
                    "attn_mode": "torch",
                },
                runtime,
                lambda _runtime: ProbeFacts(
                    "3.13.11",
                    torch_metadata_version="2.11.0+cu130",
                    cuda_available=True,
                ),
            )

            self.assertFalse(result.ok)
            self.assertTrue(
                any("network_weights" in error and "28" in error and "40" in error for error in result.errors),
                result.errors,
            )

    def test_preflight_rejects_resume_state_directory_block_metadata_mismatch(self):
        import torch
        from safetensors.torch import save_file

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            model = root / "anima-2.9b.safetensors"
            save_file(
                {
                    "net.x_embedder.proj.1.weight": torch.zeros((2048, 1)),
                    **{f"net.blocks.{index}.marker": torch.zeros(1) for index in range(40)},
                },
                model,
            )
            for name in ("vae.safetensors", "qwen.safetensors"):
                (root / name).write_bytes(b"x")
            dataset = root / "dataset"
            dataset.mkdir()
            (dataset / "a.png").write_bytes(b"png")
            (dataset / "a.txt").write_text("caption", encoding="utf-8")

            resume = root / "run-step00000028-state"
            resume.mkdir()
            save_file({"state.weight": torch.zeros(1)}, resume / "model.safetensors")
            (resume / "optimizer.bin").write_bytes(b"optimizer")
            (resume / "random_states_0.pkl").write_bytes(b"random")
            (resume / "train_state.json").write_text("{}", encoding="utf-8")
            save_file(
                {"network.weight": torch.zeros(1)},
                root / "run-step00000028.safetensors",
                metadata={"ss_num_blocks": "28"},
            )

            result = run_preflight(
                {
                    "pretrained_model_name_or_path": str(model),
                    "vae": str(root / "vae.safetensors"),
                    "qwen3": str(root / "qwen.safetensors"),
                    "train_data_dir": str(dataset),
                    "resume": str(resume),
                    "torch_compile": False,
                    "attn_mode": "torch",
                },
                runtime,
                lambda _runtime: ProbeFacts(
                    "3.13.11",
                    torch_metadata_version="2.11.0+cu130",
                    cuda_available=True,
                ),
            )

            self.assertFalse(result.ok)
            self.assertTrue(
                any("resume" in error and "28" in error and "40" in error for error in result.errors),
                result.errors,
            )

    def test_v117_latent_cache_requires_bucket_specific_key(self):
        import numpy as np

        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            np.savez(
                cache / "a_1024x1024_anima.npz",
                latents_96x128=np.zeros((1,)),
            )

            self.assertEqual(preflight_module._v117_latent_cache_stems(cache), set())

    def test_v117_latent_cache_accepts_matching_non_square_bucket_key(self):
        import numpy as np

        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            np.savez(
                cache / "a_1024x768_anima.npz",
                latents_96x128=np.zeros((1,)),
            )

            self.assertEqual(preflight_module._v117_latent_cache_stems(cache), {"a"})

    def test_v117_text_cache_requires_t5_attention_mask(self):
        import torch
        from safetensors.torch import save_file

        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            save_file(
                {
                    "crossattn_emb": torch.zeros(1),
                    "caption_dropout_rate": torch.zeros(1),
                },
                cache / "a_anima_te.safetensors",
            )

            self.assertEqual(preflight_module._v117_text_cache_stems(cache), set())

    def test_v117_text_cache_requires_caption_dropout_rate(self):
        import torch
        from safetensors.torch import save_file

        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            save_file(
                {
                    "prompt_embeds": torch.zeros(1),
                    "attn_mask": torch.zeros(1),
                    "t5_input_ids": torch.zeros(1),
                    "t5_attn_mask": torch.zeros(1),
                },
                cache / "a_anima_te.safetensors",
            )

            self.assertEqual(preflight_module._v117_text_cache_stems(cache), set())

    def test_v117_text_cache_requires_complete_variant_key_groups(self):
        import torch
        from safetensors.torch import save_file

        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            save_file(
                {
                    "num_variants": torch.tensor(2),
                    "caption_dropout_rate": torch.zeros(1),
                    "crossattn_emb_v0": torch.zeros(1),
                    "t5_attn_mask_v0": torch.zeros(1),
                    "crossattn_emb_v1": torch.zeros(1),
                },
                cache / "a_anima_te.safetensors",
            )

            self.assertEqual(preflight_module._v117_text_cache_stems(cache), set())

    def test_v117_text_cache_accepts_complete_variant_key_groups(self):
        import torch
        from safetensors.torch import save_file

        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            save_file(
                {
                    "num_variants": torch.tensor(2),
                    "caption_dropout_rate": torch.zeros(1),
                    "crossattn_emb_v0": torch.zeros(1),
                    "t5_attn_mask_v0": torch.zeros(1),
                    "crossattn_emb_v1": torch.zeros(1),
                    "t5_attn_mask_v1": torch.zeros(1),
                },
                cache / "a_anima_te.safetensors",
            )

            self.assertEqual(preflight_module._v117_text_cache_stems(cache), {"a"})

    def test_preflight_rejects_incomplete_v117_cache_sets(self):
        import numpy as np
        import torch
        from safetensors.torch import save_file

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            for name in ("model.safetensors", "vae.safetensors", "qwen.safetensors"):
                (root / name).write_bytes(b"x")
            dataset = root / "dataset"
            resized = root / "resized"
            cache = root / "cache"
            dataset.mkdir()
            resized.mkdir()
            cache.mkdir()
            for stem in ("a", "b"):
                (dataset / f"{stem}.png").write_bytes(b"png")
                (dataset / f"{stem}.txt").write_text("caption", encoding="utf-8")
                (resized / f"{stem}.png").write_bytes(b"png")
            np.savez(cache / "a_1024x1024_anima.npz", latents_1024x1024=np.zeros((1,)))
            save_file(
                {
                    "prompt_embeds": torch.zeros(1),
                    "attn_mask": torch.zeros(1),
                    "t5_input_ids": torch.zeros(1),
                    "t5_attn_mask": torch.zeros(1),
                },
                cache / "a_anima_te.safetensors",
            )

            result = run_preflight(
                {
                    "pretrained_model_name_or_path": str(root / "model.safetensors"),
                    "vae": str(root / "vae.safetensors"),
                    "qwen3": str(root / "qwen.safetensors"),
                    "train_data_dir": str(dataset),
                    "resized_image_dir": str(resized),
                    "lora_cache_dir": str(cache),
                    "use_vae_cache": True,
                    "use_text_cache": True,
                    "torch_compile": False,
                    "attn_mode": "torch",
                },
                runtime,
                lambda _runtime: ProbeFacts(
                    "3.13.11",
                    torch_metadata_version="2.11.0+cu130",
                    cuda_available=True,
                ),
            )

        self.assertFalse(result.ok)
        self.assertTrue(any("use_vae_cache=true" in error for error in result.errors))
        self.assertTrue(any("use_text_cache=true" in error for error in result.errors))

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

    def test_preflight_does_not_require_flash_attn_when_attn_mode_is_empty(self):
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
                "attn_mode": "",
            }, runtime, lambda _runtime: ProbeFacts("3.13.11", torch_metadata_version="2.11.0+cu130", cuda_available=True, flash_attn_importable=False))

        self.assertTrue(result.ok, result.errors)

    def test_preflight_requires_dynamic_compile_for_freefit(self):
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
                "compile_dynamic_seq": False,
                "torch_compile": True,
                "attn_mode": "flash",
            }, runtime, lambda _runtime: ProbeFacts("3.13.11", torch_metadata_version="2.11.0+cu130", cuda_available=True, flash_attn_importable=True))

        self.assertFalse(result.ok)
        self.assertTrue(any("compile_dynamic_seq" in error for error in result.errors))

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
                "use_vae_cache": True,
                "use_text_cache": True,
            }, runtime, lambda _runtime: ProbeFacts("3.13.11", torch_metadata_version="2.11.0+cu130", cuda_available=True, flash_attn_importable=True))

        self.assertFalse(result.ok)
        self.assertTrue(any("use_vae_cache=true requires completed" in error for error in result.errors))
        self.assertTrue(any("use_text_cache=true requires completed" in error for error in result.errors))

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

    def test_adapt_config_rejects_automagic(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            with self.assertRaises(AdapterError) as ctx:
                adapt_config(
                    {
                        "model_train_type": "anima-lora-fast",
                        "train_data_dir": str(root / "data"),
                        "optimizer_type": "Automagic",
                        "learning_rate": "1e-6",
                    },
                    runtime,
                    "run-1",
                )

        self.assertIn("Automagic", str(ctx.exception))
        self.assertIn("not supported", str(ctx.exception))

    def test_adapt_config_adds_dadapt_adagrad_eps_default(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            adapted = adapt_config(
                {
                    "model_train_type": "anima-lora-fast",
                    "train_data_dir": str(root / "data"),
                    "optimizer_type": "DAdaptAdaGrad",
                },
                runtime,
                "run-1",
            )

        self.assertIn("eps=1e-8", adapted.values["optimizer_args"])
        self.assertTrue(any("DAdaptAdaGrad" in warning and "eps=1e-8" in warning for warning in adapted.warnings))

    def test_adapt_config_keeps_user_dadapt_adagrad_eps(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            adapted = adapt_config(
                {
                    "model_train_type": "anima-lora-fast",
                    "train_data_dir": str(root / "data"),
                    "optimizer_type": "DAdaptAdaGrad",
                    "optimizer_args_custom": ["eps=1e-6", "weight_decay=0.01"],
                },
                runtime,
                "run-1",
            )

        self.assertEqual(adapted.values["optimizer_args"], ["eps=1e-6", "weight_decay=0.01"])
        self.assertFalse(any("eps=1e-8" in warning for warning in adapted.warnings))

    def test_preflight_accepts_v117_dynamic_compile_contract(self):
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
                    "gradient_checkpointing": True,
                    "torch_compile": True,
                    "compile_dynamic_seq": True,
                    "attn_mode": "torch",
                },
                runtime,
                lambda _runtime: ProbeFacts("3.13.11", torch_metadata_version="2.11.0+cu130", cuda_available=True),
            )

        self.assertTrue(result.ok, result.errors)

    def test_adapt_config_ignores_removed_compile_mode(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            adapted = adapt_config(
                {
                    "model_train_type": "anima-lora-fast",
                    "train_data_dir": str(root / "data"),
                    "compile_mode": "full",
                    "gradient_checkpointing": True,
                },
                runtime,
                "run-1",
            )

        self.assertNotIn("compile_mode", adapted.values)
        self.assertTrue(any("compile_mode" in w for w in adapted.warnings))

    def test_preflight_rejects_automagic_even_when_quanto_is_available(self):
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
                    quanto_importable=True,
                ),
            )

        self.assertFalse(result.ok)
        self.assertTrue(any("Automagic" in err and "not supported" in err for err in result.errors))

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
        self.assertEqual(spec.env["ACCELERATE_DISABLE_RICH"], "1")
        self.assertEqual(spec.env["NO_COLOR"], "1")
        self.assertEqual(spec.env["FORCE_COLOR"], "0")
        self.assertEqual(spec.env["TERM"], "dumb")


if __name__ == "__main__":
    unittest.main()

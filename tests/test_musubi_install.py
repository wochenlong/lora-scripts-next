from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mikazuki.musubi_backend.environment import (
    build_environment_install_plan,
    resolve_cuda_extra,
)
from mikazuki.musubi_backend.extension_state import (
    STATE_BROKEN,
    STATE_INSTALLED_UNVERIFIED,
    STATE_NOT_INSTALLED,
    STATE_READY,
    default_layout,
    read_extension_status,
    write_install_state,
)
from mikazuki.musubi_backend.installer import (
    build_install_plan,
    copy_source_snapshot,
    remove_extension,
)
from mikazuki.musubi_backend.preflight import ProbeFacts, run_preflight
from mikazuki.musubi_backend.settings import (
    RuntimeConfig,
    default_upstream_cache,
    discover_runtime,
    ensure_install_source_ready,
    resolve_install_source_root,
)


def make_source(root: Path) -> Path:
    source = root / "upstream"
    (source / "src" / "musubi_tuner").mkdir(parents=True)
    (source / "src" / "musubi_tuner" / "__init__.py").write_text("", encoding="utf-8")
    (source / "pyproject.toml").write_text("[project]\nname = \"musubi-tuner\"\n", encoding="utf-8")
    (source / "krea2_train_network.py").write_text("# entry\n", encoding="utf-8")
    (source / "krea2_cache_latents.py").write_text("# entry\n", encoding="utf-8")
    (source / ".venv").mkdir()
    (source / ".venv" / "junk.txt").write_text("x", encoding="utf-8")
    return source


def make_runtime(root: Path) -> RuntimeConfig:
    return RuntimeConfig(
        musubi_root=(root / "vendor" / "musubi-tuner").resolve(),
        python=(root / "vendor" / "musubi-tuner" / ".venv" / "Scripts" / "python.exe").resolve(),
        lora_next_root=root.resolve(),
        output_dir=(root / "output" / "musubi").resolve(),
        logging_dir=(root / "logs" / "musubi").resolve(),
        cache_dir=(root / ".cache" / "musubi").resolve(),
    )


class ExtensionStateTests(unittest.TestCase):
    def test_missing_root_is_not_installed(self):
        with tempfile.TemporaryDirectory() as td:
            status = read_extension_status(default_layout(Path(td)))
        self.assertEqual(status.state, STATE_NOT_INSTALLED)

    def test_source_without_venv_is_installed_unverified(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            layout = default_layout(root)
            (layout.source / "src" / "musubi_tuner").mkdir(parents=True)
            (layout.source / "pyproject.toml").write_text("", encoding="utf-8")
            (layout.source / "krea2_train_network.py").write_text("", encoding="utf-8")
            status = read_extension_status(layout)
        self.assertEqual(status.state, STATE_INSTALLED_UNVERIFIED)

    def test_ready_requires_passing_audit_facts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            layout = default_layout(root)
            (layout.source / "src" / "musubi_tuner").mkdir(parents=True)
            (layout.source / "pyproject.toml").write_text("", encoding="utf-8")
            (layout.source / "krea2_train_network.py").write_text("", encoding="utf-8")
            layout.venv_python.parent.mkdir(parents=True)
            layout.venv_python.write_text("", encoding="utf-8")
            write_install_state(layout, STATE_READY, {"audit": {"ok": False}})
            status = read_extension_status(layout)
            self.assertEqual(status.state, STATE_INSTALLED_UNVERIFIED)
            write_install_state(layout, STATE_READY, {"audit": {"ok": True}})
            status = read_extension_status(layout)
            self.assertEqual(status.state, STATE_READY)

    def test_missing_runtime_files_mark_broken(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            layout = default_layout(root)
            layout.source.mkdir(parents=True)
            status = read_extension_status(layout)
        self.assertEqual(status.state, STATE_BROKEN)


class InstallerTests(unittest.TestCase):
    def test_copy_source_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = make_source(root)
            layout = default_layout(root)
            plan = build_install_plan(source, layout, dry_run=False)
            copy_source_snapshot(plan)

            self.assertTrue((layout.source / "src" / "musubi_tuner" / "__init__.py").is_file())
            self.assertTrue((layout.source / "pyproject.toml").is_file())
            self.assertTrue((layout.source / "krea2_train_network.py").is_file())
            self.assertTrue((layout.source / "krea2_cache_latents.py").is_file())
            self.assertFalse((layout.source / ".venv").exists())

    def test_copy_source_snapshot_requires_package(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bad = root / "bad"
            bad.mkdir()
            plan = build_install_plan(bad, default_layout(root), dry_run=False)
            with self.assertRaises(FileNotFoundError):
                copy_source_snapshot(plan)

    def test_remove_extension_refuses_outside_extensions(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            from mikazuki.musubi_backend.extension_state import ExtensionLayout

            outside = ExtensionLayout(root / "somewhere" / "else")
            with self.assertRaises(ValueError):
                remove_extension(outside, root)

    def test_resolve_install_source_root_finds_vendor(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "vendor" / "musubi-tuner" / "src" / "musubi_tuner").mkdir(parents=True)
            found = resolve_install_source_root(root)
            self.assertEqual(found, (root / "vendor" / "musubi-tuner").resolve())

    def test_resolve_install_source_root_errors_when_absent(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                resolve_install_source_root(Path(td))

    def test_resolve_install_source_root_prefers_existing_cache(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache = default_upstream_cache(root)
            (cache / "src" / "musubi_tuner").mkdir(parents=True)
            self.assertEqual(resolve_install_source_root(root), cache)

    def test_resolve_install_source_root_clones_when_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache = default_upstream_cache(root)

            def fake_run(cmd, **kwargs):
                if cmd[:2] == ["git", "clone"]:
                    (cache / "src" / "musubi_tuner").mkdir(parents=True)
                return subprocess.CompletedProcess(cmd, 0)

            with mock.patch("mikazuki.musubi_backend.settings.subprocess.run", side_effect=fake_run) as run:
                found = resolve_install_source_root(root, allow_clone=True)
            self.assertEqual(found, cache)
            clone_cmd = run.call_args_list[0].args[0]
            self.assertIn("https://github.com/kohya-ss/musubi-tuner.git", clone_cmd)

    def test_ensure_install_source_ready_keeps_usable_preferred(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            preferred = root / "elsewhere"
            (preferred / "src" / "musubi_tuner").mkdir(parents=True)
            with mock.patch("mikazuki.musubi_backend.settings.subprocess.run") as run:
                found = ensure_install_source_ready(root, preferred)
            self.assertEqual(found, preferred.resolve())
            run.assert_not_called()


class EnvironmentPlanTests(unittest.TestCase):
    def test_cuda_extra_resolution(self):
        self.assertEqual(resolve_cuda_extra(config={}, env={}), "cu128")
        self.assertEqual(resolve_cuda_extra(config={}, env={"MUSUBI_CUDA_EXTRA": "cu130"}), "cu130")
        self.assertEqual(resolve_cuda_extra(config={}, env={"MUSUBI_CUDA_EXTRA": "bogus"}), "cu128")
        self.assertEqual(resolve_cuda_extra(config={"backend": {"cuda_extra": "cu124"}}, env={}), "cu124")

    def test_install_plan_layout(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            layout = default_layout(root)
            plan = build_environment_install_plan(root, layout, root / "upstream", cuda_extra="cu130")
            self.assertEqual(plan.venv_python, layout.venv_python)
            self.assertEqual(plan.cuda_extra, "cu130")
            self.assertTrue(plan.as_dict()["target_source"].endswith("source"))


class SettingsDiscoveryTests(unittest.TestCase):
    def test_prefers_extension_layout_source(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            layout = default_layout(root)
            (layout.source / "src" / "musubi_tuner").mkdir(parents=True)
            layout.venv_python.parent.mkdir(parents=True)
            layout.venv_python.write_text("", encoding="utf-8")
            runtime = discover_runtime(config={}, lora_next_root=root)
            self.assertEqual(runtime.musubi_root, layout.source.resolve())
            self.assertEqual(runtime.python.resolve(), layout.venv_python.resolve())

    def test_falls_back_to_vendor(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = discover_runtime(config={}, lora_next_root=root)
            self.assertEqual(runtime.musubi_root, (root / "vendor" / "musubi-tuner").resolve())


class PreflightTests(unittest.TestCase):
    def _values_and_dataset(self, root: Path) -> tuple[dict, dict]:
        models = root / "models"
        models.mkdir(exist_ok=True)
        for name in ("dit.safetensors", "vae.safetensors", "te.safetensors"):
            (models / name).write_text("x", encoding="utf-8")
        train = root / "train" / "4_char"
        train.mkdir(parents=True)
        (train / "a.png").write_text("x", encoding="utf-8")
        (train / "a.txt").write_text("caption", encoding="utf-8")
        values = {
            "dit": str(models / "dit.safetensors"),
            "vae": str(models / "vae.safetensors"),
            "text_encoder": str(models / "te.safetensors"),
        }
        dataset = {
            "general": {"caption_extension": ".txt"},
            "datasets": [{"image_directory": str(train), "cache_directory": str(root / "cache"), "num_repeats": 4}],
        }
        return values, dataset

    def test_ok_with_fake_probe(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            runtime.python.parent.mkdir(parents=True, exist_ok=True)
            runtime.python.write_text("", encoding="utf-8")
            values, dataset = self._values_and_dataset(root)
            probe = lambda rt: ProbeFacts(  # noqa: E731
                python_version="3.12.0",
                torch_version="2.7.1+cu128",
                cuda_available=True,
                transformers_version="4.57.6",
                vram_total_mb=24576,
            )
            result = run_preflight(values, runtime, dataset, probe=probe)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.facts["dataset_image_count"], 1)

    def test_missing_model_file_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            values, dataset = self._values_and_dataset(root)
            values["dit"] = str(root / "models" / "missing.safetensors")
            probe = lambda rt: ProbeFacts()  # noqa: E731
            result = run_preflight(values, runtime, dataset, probe=probe)
        self.assertFalse(result.ok)
        self.assertTrue(any("dit" in e for e in result.errors))

    def test_old_transformers_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            runtime.python.parent.mkdir(parents=True, exist_ok=True)
            runtime.python.write_text("", encoding="utf-8")
            values, dataset = self._values_and_dataset(root)
            probe = lambda rt: ProbeFacts(  # noqa: E731
                python_version="3.12.0",
                cuda_available=True,
                transformers_version="4.51.3",
            )
            result = run_preflight(values, runtime, dataset, probe=probe)
        self.assertFalse(result.ok)
        self.assertTrue(any("transformers" in e for e in result.errors))


if __name__ == "__main__":
    unittest.main()

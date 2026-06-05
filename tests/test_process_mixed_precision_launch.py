"""Tests for accelerate launch mixed_precision forwarding in mikazuki.process."""

from __future__ import annotations

import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


def _install_stub_modules() -> None:
    app_pkg = types.ModuleType("mikazuki.app")
    app_pkg.__path__ = []  # type: ignore[attr-defined]
    models_mod = types.ModuleType("mikazuki.app.models")

    class _APIResponse:
        def __init__(self, status: str = "success", message: str = "", data=None):
            self.status = status
            self.message = message
            self.data = data or {}

    models_mod.APIResponse = _APIResponse
    sys.modules.setdefault("mikazuki.app", app_pkg)
    sys.modules["mikazuki.app.models"] = models_mod

    log_mod = types.ModuleType("mikazuki.log")
    log_mod.log = mock.MagicMock()
    sys.modules["mikazuki.log"] = log_mod

    tasks_mod = types.ModuleType("mikazuki.tasks")
    tasks_mod.tm = mock.MagicMock()
    sys.modules["mikazuki.tasks"] = tasks_mod

    launch_mod = types.ModuleType("mikazuki.launch_utils")
    launch_mod.base_dir_path = lambda: "."
    sys.modules["mikazuki.launch_utils"] = launch_mod

    portable_mod = types.ModuleType("mikazuki.portable_utils")
    portable_mod.train_env_overrides = lambda: {}
    sys.modules["mikazuki.portable_utils"] = portable_mod

    if "toml" not in sys.modules:

        def _simple_toml_loads(text: str) -> dict:
            result: dict = {}
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                result[key.strip()] = val.strip().strip('"').strip("'")
            return result

        toml_mod = types.ModuleType("toml")
        toml_mod.loads = _simple_toml_loads
        sys.modules["toml"] = toml_mod

    fast_mod = types.ModuleType("mikazuki.anima_fast_backend.launcher")
    fast_mod.build_launch_spec = mock.MagicMock()
    sys.modules["mikazuki.anima_fast_backend.launcher"] = fast_mod

    resolver_mod = types.ModuleType("mikazuki.anima_fast_backend.service_resolver")
    resolver_mod.default_resolver = mock.MagicMock()
    sys.modules["mikazuki.anima_fast_backend.service_resolver"] = resolver_mod


_install_stub_modules()
process = importlib.import_module("mikazuki.process")


class NormalizeMixedPrecisionTests(unittest.TestCase):
    def test_valid_values(self):
        self.assertEqual(process.normalize_mixed_precision("bf16"), "bf16")
        self.assertEqual(process.normalize_mixed_precision(" FP16 "), "fp16")
        self.assertEqual(process.normalize_mixed_precision("no"), "no")

    def test_invalid_or_empty(self):
        self.assertIsNone(process.normalize_mixed_precision(None))
        self.assertIsNone(process.normalize_mixed_precision(""))
        self.assertIsNone(process.normalize_mixed_precision("fp32"))


class BuildAccelerateTrainCommandTests(unittest.TestCase):
    def test_forwards_bf16_from_toml(self):
        with tempfile.TemporaryDirectory() as tmp:
            toml_path = Path(tmp) / "train.toml"
            toml_path.write_text('mixed_precision = "bf16"\n', encoding="utf-8")
            args, _env, mp = process.build_accelerate_train_command(
                trainer_file="./scripts/stable/train_network.py",
                toml_path=str(toml_path),
            )

        self.assertEqual(mp, "bf16")
        self.assertIn("--mixed_precision", args)
        idx = args.index("--mixed_precision")
        self.assertEqual(args[idx + 1], "bf16")
        self.assertEqual(args[-2:], ["--config_file", str(toml_path)])

    def test_omits_flag_when_toml_has_no_mixed_precision(self):
        with tempfile.TemporaryDirectory() as tmp:
            toml_path = Path(tmp) / "train.toml"
            toml_path.write_text('output_dir = "out"\n', encoding="utf-8")
            args, _env, mp = process.build_accelerate_train_command(
                trainer_file="./scripts/stable/train_network.py",
                toml_path=str(toml_path),
            )

        self.assertIsNone(mp)
        self.assertNotIn("--mixed_precision", args)

    def test_multi_gpu_inserts_before_launch_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            toml_path = Path(tmp) / "train.toml"
            toml_path.write_text('mixed_precision = "bf16"\n', encoding="utf-8")
            args, env, _mp = process.build_accelerate_train_command(
                trainer_file="./scripts/stable/train_network.py",
                toml_path=str(toml_path),
                gpu_ids=["0", "1"],
            )

        self.assertIn("--multi_gpu", args)
        self.assertIn("--mixed_precision", args)
        self.assertLess(args.index("--multi_gpu"), args.index("--mixed_precision"))
        self.assertEqual(env["CUDA_VISIBLE_DEVICES"], "0,1")

    def test_disables_colored_subprocess_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            toml_path = Path(tmp) / "train.toml"
            toml_path.write_text('mixed_precision = "bf16"\n', encoding="utf-8")
            _args, env, _mp = process.build_accelerate_train_command(
                trainer_file="./scripts/stable/train_network.py",
                toml_path=str(toml_path),
            )

        self.assertEqual(env["ACCELERATE_DISABLE_RICH"], "1")
        self.assertEqual(env["NO_COLOR"], "1")
        self.assertEqual(env["FORCE_COLOR"], "0")
        self.assertEqual(env["TERM"], "dumb")


if __name__ == "__main__":
    unittest.main()

"""Tests for accelerate launch mixed_precision forwarding in mikazuki.process."""

from __future__ import annotations

import importlib
import enum
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


# sys.modules keys this module replaces with stand-ins (plus mikazuki.process,
# imported below). They are snapshotted before stubbing and restored in
# tearDownModule so stubs do not leak into later tests collected in the same
# process (see issue #95).
_STUBBED_MODULE_NAMES = (
    "mikazuki.app",
    "mikazuki.app.models",
    "mikazuki.log",
    "mikazuki.tasks",
    "mikazuki.launch_utils",
    "mikazuki.portable_utils",
    "toml",
    "mikazuki.engines.anima_fast.launcher",
    "mikazuki.engines.anima_fast.service_resolver",
    "mikazuki.process",
)
_SAVED_MODULES: dict[str, types.ModuleType | None] = {}


def _snapshot_modules() -> None:
    for name in _STUBBED_MODULE_NAMES:
        _SAVED_MODULES[name] = sys.modules.get(name)


def _restore_modules() -> None:
    for name, original in _SAVED_MODULES.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original
    _SAVED_MODULES.clear()


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

    class _TaskStatus(enum.Enum):  # process.py only reads TaskStatus.QUEUED
        QUEUED = 5

    tasks_mod.TaskStatus = _TaskStatus
    sys.modules["mikazuki.tasks"] = tasks_mod

    launch_mod = types.ModuleType("mikazuki.launch_utils")
    launch_mod.base_dir_path = lambda: Path("/project/root")
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

    fast_mod = types.ModuleType("mikazuki.engines.anima_fast.launcher")
    fast_mod.build_launch_spec = mock.MagicMock()
    sys.modules["mikazuki.engines.anima_fast.launcher"] = fast_mod

    resolver_mod = types.ModuleType("mikazuki.engines.anima_fast.service_resolver")
    resolver_mod.default_resolver = mock.MagicMock()
    sys.modules["mikazuki.engines.anima_fast.service_resolver"] = resolver_mod

    sys.modules.pop("mikazuki.process", None)


# Install stubs only long enough to import ``mikazuki.process``; the imported
# module keeps its own references to whatever it pulled in, so we restore
# sys.modules immediately to avoid leaking stubs into later test modules that
# are imported in the same collection pass (issue #95).
_snapshot_modules()
_install_stub_modules()
try:
    process = importlib.import_module("mikazuki.process")
finally:
    _restore_modules()


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

    def _assert_launch_opts_intact(self, args, trainer_file):
        """Every launch option must keep its flag/value pairs intact and sit
        before the trainer script (regression for issue #324, where multi-gpu
        args were spliced into the middle of `--num_cpu_threads_per_process`'s
        value)."""
        trainer_idx = args.index(trainer_file)
        launch_opts = args[2:trainer_idx]

        threads_idx = launch_opts.index("--num_cpu_threads_per_process")
        self.assertTrue(launch_opts[threads_idx + 1].isdigit())

        # No option token may be immediately followed by another known flag
        # when a value is expected.
        for flag_with_value in ("--num_cpu_threads_per_process", "--num_processes", "--mixed_precision"):
            if flag_with_value in launch_opts:
                idx = launch_opts.index(flag_with_value)
                self.assertFalse(launch_opts[idx + 1].startswith("--"))
        return launch_opts

    def test_multi_gpu_launch_opts_structure(self):
        trainer = "./scripts/stable/train_network.py"
        with tempfile.TemporaryDirectory() as tmp:
            toml_path = Path(tmp) / "train.toml"
            toml_path.write_text('mixed_precision = "bf16"\n', encoding="utf-8")
            args, env, _mp = process.build_accelerate_train_command(
                trainer_file=trainer,
                toml_path=str(toml_path),
                gpu_ids=["0", "1"],
            )

        launch_opts = self._assert_launch_opts_intact(args, trainer)
        self.assertIn("--multi_gpu", launch_opts)
        num_proc_idx = launch_opts.index("--num_processes")
        self.assertEqual(launch_opts[num_proc_idx + 1], "2")
        self.assertNotIn("--rdzv_backend", launch_opts)
        self.assertEqual(env["CUDA_VISIBLE_DEVICES"], "0,1")
        self.assertNotIn("USE_LIBUV", env)

    def test_multi_gpu_windows_variant(self):
        trainer = "./scripts/stable/train_network.py"
        with tempfile.TemporaryDirectory() as tmp:
            toml_path = Path(tmp) / "train.toml"
            toml_path.write_text('mixed_precision = "bf16"\n', encoding="utf-8")
            with mock.patch.object(process.sys, "platform", "win32"):
                args, env, _mp = process.build_accelerate_train_command(
                    trainer_file=trainer,
                    toml_path=str(toml_path),
                    gpu_ids=["0", "1"],
                )

        launch_opts = self._assert_launch_opts_intact(args, trainer)
        self.assertIn("--multi_gpu", launch_opts)
        rdzv_idx = launch_opts.index("--rdzv_backend")
        self.assertEqual(launch_opts[rdzv_idx + 1], "c10d")
        self.assertEqual(env["USE_LIBUV"], "0")

    def test_multi_gpu_opts_parse_with_accelerate_argparse(self):
        """Smoke test: the assembled launch options must be accepted by
        accelerate's real launch argument parser (issue #324)."""
        pytest = importlib.import_module("pytest")
        accelerate_launch = pytest.importorskip("accelerate.commands.launch")
        trainer = "./scripts/stable/train_network.py"
        with tempfile.TemporaryDirectory() as tmp:
            toml_path = Path(tmp) / "train.toml"
            toml_path.write_text('mixed_precision = "bf16"\n', encoding="utf-8")
            args, _env, _mp = process.build_accelerate_train_command(
                trainer_file=trainer,
                toml_path=str(toml_path),
                gpu_ids=["0", "1"],
            )

        parser = accelerate_launch.launch_command_parser()
        launch_opts = args[2 : args.index(trainer)]
        ns = parser.parse_args([*launch_opts, trainer])
        self.assertTrue(ns.multi_gpu)
        self.assertEqual(ns.num_processes, 2)
        self.assertEqual(ns.num_cpu_threads_per_process, 2)

    def test_single_gpu_keeps_launch_opts_intact(self):
        trainer = "./scripts/stable/train_network.py"
        with tempfile.TemporaryDirectory() as tmp:
            toml_path = Path(tmp) / "train.toml"
            toml_path.write_text('mixed_precision = "bf16"\n', encoding="utf-8")
            args, env, _mp = process.build_accelerate_train_command(
                trainer_file=trainer,
                toml_path=str(toml_path),
                gpu_ids=["0"],
            )

        launch_opts = self._assert_launch_opts_intact(args, trainer)
        self.assertNotIn("--multi_gpu", launch_opts)
        self.assertEqual(env["CUDA_VISIBLE_DEVICES"], "0")

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

    def test_disables_user_site_when_training_deps_do_not_need_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            toml_path = Path(tmp) / "train.toml"
            toml_path.write_text('mixed_precision = "bf16"\n', encoding="utf-8")
            with mock.patch.object(process, "_module_origin_under_user_site", return_value=False):
                _args, env, _mp = process.build_accelerate_train_command(
                    trainer_file="./scripts/stable/train_network.py",
                    toml_path=str(toml_path),
                )

        self.assertEqual(env["PYTHONNOUSERSITE"], "1")

    def test_allows_user_site_when_torch_is_installed_there(self):
        def _under_user_site(name: str) -> bool:
            return name == "torch"

        with tempfile.TemporaryDirectory() as tmp:
            toml_path = Path(tmp) / "train.toml"
            toml_path.write_text('mixed_precision = "bf16"\n', encoding="utf-8")
            with mock.patch.object(process, "_module_origin_under_user_site", side_effect=_under_user_site):
                _args, env, _mp = process.build_accelerate_train_command(
                    trainer_file="./scripts/stable/train_network.py",
                    toml_path=str(toml_path),
                )

        self.assertNotIn("PYTHONNOUSERSITE", env)

    def test_injects_project_root_onto_pythonpath(self):
        """Regression for #158: accelerate_launch.py imports mikazuki, so the
        project root must be on PYTHONPATH for portable installs."""
        with tempfile.TemporaryDirectory() as tmp:
            toml_path = Path(tmp) / "train.toml"
            toml_path.write_text('mixed_precision = "bf16"\n', encoding="utf-8")
            with mock.patch.dict("os.environ", {}, clear=False):
                import os

                os.environ.pop("PYTHONPATH", None)
                _args, env, _mp = process.build_accelerate_train_command(
                    trainer_file="./scripts/stable/train_network.py",
                    toml_path=str(toml_path),
                )

        self.assertEqual(env["PYTHONPATH"], str(Path("/project/root")))

    def test_prepends_project_root_preserving_existing_pythonpath(self):
        import os

        existing = os.pathsep.join(["/already/here", "/second"])
        with tempfile.TemporaryDirectory() as tmp:
            toml_path = Path(tmp) / "train.toml"
            toml_path.write_text('mixed_precision = "bf16"\n', encoding="utf-8")
            with mock.patch.dict("os.environ", {"PYTHONPATH": existing}, clear=False):
                _args, env, _mp = process.build_accelerate_train_command(
                    trainer_file="./scripts/stable/train_network.py",
                    toml_path=str(toml_path),
                )

        parts = env["PYTHONPATH"].split(os.pathsep)
        self.assertEqual(parts[0], str(Path("/project/root")))
        self.assertIn("/already/here", parts)
        self.assertIn("/second", parts)


if __name__ == "__main__":
    unittest.main()

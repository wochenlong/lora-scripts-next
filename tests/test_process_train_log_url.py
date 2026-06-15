"""Tests for the train-log URL banner emitted by ``mikazuki.process.run_train``.

``mikazuki.process`` pulls in FastAPI through ``mikazuki.app.models``. To keep
this test runnable without the full GUI runtime dependencies installed, we
stub out the heavy modules before importing ``mikazuki.process``.
"""

from __future__ import annotations

import importlib
import sys
import types
import unittest
from unittest import mock


# sys.modules keys this module replaces with stand-ins (plus mikazuki.process,
# imported below). Snapshotted before stubbing and restored in tearDownModule
# so stubs do not leak into later tests in the same process (see issue #95).
_STUBBED_MODULE_NAMES = (
    "mikazuki.app",
    "mikazuki.app.models",
    "mikazuki.log",
    "mikazuki.tasks",
    "mikazuki.launch_utils",
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
    """Inject minimal stand-in modules so ``mikazuki.process`` imports cleanly."""

    # mikazuki.app.models — only APIResponse is referenced.
    app_pkg = types.ModuleType("mikazuki.app")
    app_pkg.__path__ = []  # type: ignore[attr-defined]
    models_mod = types.ModuleType("mikazuki.app.models")

    class _APIResponse:  # pragma: no cover - trivial container
        def __init__(self, status: str = "success", message: str = "", data=None):
            self.status = status
            self.message = message
            self.data = data or {}

    models_mod.APIResponse = _APIResponse
    sys.modules.setdefault("mikazuki.app", app_pkg)
    sys.modules["mikazuki.app.models"] = models_mod

    # mikazuki.log — provide a no-op logger.
    log_mod = types.ModuleType("mikazuki.log")
    log_mod.log = mock.MagicMock()
    sys.modules["mikazuki.log"] = log_mod

    # mikazuki.tasks — provide a stub ``tm`` with ``create_task``.
    tasks_mod = types.ModuleType("mikazuki.tasks")
    tasks_mod.tm = mock.MagicMock()
    sys.modules["mikazuki.tasks"] = tasks_mod

    # mikazuki.launch_utils — ``base_dir_path`` is imported but not used in the
    # tested functions.
    launch_mod = types.ModuleType("mikazuki.launch_utils")
    launch_mod.base_dir_path = lambda: "."
    sys.modules["mikazuki.launch_utils"] = launch_mod


# Install stubs only long enough to import ``mikazuki.process``; restore
# sys.modules immediately so the stubs do not leak into later test modules
# imported in the same collection pass (issue #95).
_snapshot_modules()
_install_stub_modules()
try:
    process = importlib.import_module("mikazuki.process")
finally:
    _restore_modules()


class BuildTrainLogUrlsTests(unittest.TestCase):
    def test_defaults_when_env_missing(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            for var in ("MIKAZUKI_HOST", "MIKAZUKI_PORT"):
                if var in __import__("os").environ:
                    del __import__("os").environ[var]
            urls = process.build_train_log_urls("task-1")

        self.assertEqual(urls["base"], "http://127.0.0.1:28000")
        self.assertEqual(urls["viewer"], "http://127.0.0.1:28000/train-log?task_id=task-1")
        self.assertEqual(urls["stream"], "http://127.0.0.1:28000/api/train/log/stream/task-1")

    def test_uses_host_and_port_env(self):
        with mock.patch.dict(
            "os.environ",
            {"MIKAZUKI_HOST": "10.0.0.5", "MIKAZUKI_PORT": "9000"},
            clear=False,
        ):
            urls = process.build_train_log_urls("xyz")

        self.assertEqual(urls["viewer"], "http://10.0.0.5:9000/train-log?task_id=xyz")
        self.assertEqual(urls["stream"], "http://10.0.0.5:9000/api/train/log/stream/xyz")

    def test_substitutes_unspecified_host(self):
        for host in ("0.0.0.0", "::", ""):
            with self.subTest(host=host):
                with mock.patch.dict(
                    "os.environ",
                    {"MIKAZUKI_HOST": host, "MIKAZUKI_PORT": "28000"},
                    clear=False,
                ):
                    urls = process.build_train_log_urls("t")
                self.assertEqual(urls["base"], "http://127.0.0.1:28000")


class AnnounceTrainLogTests(unittest.TestCase):
    def test_no_auto_open_by_default(self):
        urls = {"viewer": "http://x/v", "stream": "http://x/s", "base": "http://x"}
        with mock.patch.dict("os.environ", {}, clear=False), \
                mock.patch.object(process, "webbrowser") as wb, \
                mock.patch.object(process, "log") as log_mock:
            if "MIKAZUKI_AUTO_OPEN_TRAIN_LOG" in __import__("os").environ:
                del __import__("os").environ["MIKAZUKI_AUTO_OPEN_TRAIN_LOG"]
            process._announce_train_log("tid", urls)

        wb.open.assert_not_called()
        log_mock.info.assert_called_once()
        banner = log_mock.info.call_args.args[0]
        self.assertIn("http://x/v", banner)
        self.assertIn("http://x/s", banner)
        self.assertIn("tid", banner)

    def test_auto_open_when_env_truthy(self):
        urls = {"viewer": "http://x/v", "stream": "http://x/s", "base": "http://x"}
        for value in ("1", "true", "YES", "on"):
            with self.subTest(value=value):
                with mock.patch.dict(
                    "os.environ",
                    {"MIKAZUKI_AUTO_OPEN_TRAIN_LOG": value},
                    clear=False,
                ), mock.patch.object(process, "webbrowser") as wb, \
                        mock.patch.object(process, "log"):
                    process._announce_train_log("tid", urls)
                wb.open.assert_called_once_with("http://x/v")

    def test_auto_open_failure_is_swallowed(self):
        urls = {"viewer": "http://x/v", "stream": "http://x/s", "base": "http://x"}
        with mock.patch.dict(
            "os.environ",
            {"MIKAZUKI_AUTO_OPEN_TRAIN_LOG": "1"},
            clear=False,
        ), mock.patch.object(process, "webbrowser") as wb, \
                mock.patch.object(process, "log") as log_mock:
            wb.open.side_effect = RuntimeError("no display")
            # Should not raise.
            process._announce_train_log("tid", urls)

        log_mock.warning.assert_called_once()


class TruthyEnvTests(unittest.TestCase):
    def test_truthy_values(self):
        for value in ("1", "true", "YES", " on "):
            with self.subTest(value=value):
                with mock.patch.dict("os.environ", {"MIKAZUKI_TEST_FLAG": value}, clear=False):
                    self.assertTrue(process._truthy_env("MIKAZUKI_TEST_FLAG"))

    def test_falsy_values(self):
        for value in ("0", "false", "", "no", "off", "anything-else"):
            with self.subTest(value=value):
                with mock.patch.dict("os.environ", {"MIKAZUKI_TEST_FLAG": value}, clear=False):
                    self.assertFalse(process._truthy_env("MIKAZUKI_TEST_FLAG"))


class RunTrainMetadataTests(unittest.TestCase):
    def test_run_train_returns_metadata_for_observability(self):
        task = mock.MagicMock()
        task.task_id = "task-meta"

        with mock.patch.object(process.tm, "create_task", return_value=task) as create_task, \
                mock.patch.object(process, "asyncio") as asyncio_mock, \
                mock.patch.object(process, "_announce_train_log"), \
                mock.patch.object(process, "build_train_log_urls", return_value={
                    "base": "http://127.0.0.1:28000",
                    "viewer": "http://127.0.0.1:28000/train-log?task_id=task-meta",
                    "stream": "http://127.0.0.1:28000/api/train/log/stream/task-meta",
                }), \
                mock.patch.object(process, "read_mixed_precision_from_train_toml", return_value="bf16"):
            asyncio_mock.to_thread.return_value = object()
            response = process.run_train(
                "config/autosave/test.toml",
                "./scripts/stable/train_network.py",
                gpu_ids=["0"],
                cpu_threads=4,
            )

        self.assertEqual(response.status, "success")
        create_task.assert_called_once()
        metadata = create_task.call_args.kwargs["metadata"]
        self.assertEqual(metadata["backend"], "standard")
        self.assertEqual(metadata["trainer_file"], "./scripts/stable/train_network.py")
        self.assertEqual(metadata["mixed_precision"], "bf16")
        self.assertEqual(metadata["cpu_threads"], 4)
        self.assertEqual(metadata["gpu_ids"], ["0"])
        self.assertIn("command", metadata)
        self.assertEqual(response.data["metadata"], metadata)
        self.assertEqual(response.data["config_path"], metadata["config_path"])
        self.assertEqual(response.data["trainer_file"], "./scripts/stable/train_network.py")

    def test_run_train_preserves_extra_metadata_warnings(self):
        task = mock.MagicMock()
        task.task_id = "task-warning"

        with mock.patch.object(process.tm, "create_task", return_value=task) as create_task, \
                mock.patch.object(process, "asyncio") as asyncio_mock, \
                mock.patch.object(process, "_announce_train_log"), \
                mock.patch.object(process, "build_train_log_urls", return_value={
                    "base": "http://127.0.0.1:28000",
                    "viewer": "http://127.0.0.1:28000/train-log?task_id=task-warning",
                    "stream": "http://127.0.0.1:28000/api/train/log/stream/task-warning",
                }), \
                mock.patch.object(process, "read_mixed_precision_from_train_toml", return_value="bf16"):
            asyncio_mock.to_thread.return_value = object()
            response = process.run_train(
                "config/autosave/test.toml",
                "./scripts/dev/anima_train_network.py",
                cpu_threads=2,
                metadata={"warnings": ["guardrail active"]},
            )

        metadata = create_task.call_args.kwargs["metadata"]
        self.assertEqual(response.status, "success")
        self.assertEqual(metadata["warnings"], ["guardrail active"])
        self.assertEqual(response.data["metadata"]["warnings"], ["guardrail active"])

    def test_run_train_create_task_failure_returns_diagnostic_data(self):
        with mock.patch.object(process.tm, "create_task", return_value=None), \
                mock.patch.object(process, "read_mixed_precision_from_train_toml", return_value=None):
            response = process.run_train(
                "config/autosave/test.toml",
                "./scripts/stable/train_network.py",
                gpu_ids=None,
                cpu_threads=2,
            )

        self.assertEqual(response.status, "error")
        self.assertIn("trainer_file", response.data)
        self.assertIn("config_path", response.data)
        self.assertEqual(response.data["backend"], "standard")


if __name__ == "__main__":
    unittest.main()

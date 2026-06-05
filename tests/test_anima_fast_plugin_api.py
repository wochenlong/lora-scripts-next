from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from starlette.requests import Request

from mikazuki.anima_fast_backend.extension_state import ExtensionLayout, STATE_READY, write_install_state
from mikazuki.anima_fast_backend.preflight import PreflightResult
from mikazuki.anima_fast_backend.settings import discover_runtime
from mikazuki.app import api


def make_request(payload: dict) -> Request:
    body = json.dumps(payload).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": "POST", "path": "/api/test", "headers": []}, receive)


class AnimaFastPluginApiTests(unittest.TestCase):
    def setUp(self):
        self.previous = os.environ.get("LORA_ENABLE_ANIMA_FAST")
        os.environ["LORA_ENABLE_ANIMA_FAST"] = "1"

    def tearDown(self):
        if self.previous is None:
            os.environ.pop("LORA_ENABLE_ANIMA_FAST", None)
        else:
            os.environ["LORA_ENABLE_ANIMA_FAST"] = self.previous

    def test_preflight_fail_message_includes_errors(self):
        result = PreflightResult(
            ok=False,
            errors=["anima_lora requires Python 3.13.*, got 3.12.0", "torch.cuda is not available"],
        )
        response = api._anima_fast_fail_from_preflight(result)
        self.assertEqual(response.status, "fail")
        self.assertIn("Python 3.13", response.message)
        self.assertIn("预检查失败", response.message)

    def test_discover_runtime_prefers_extension_venv_over_external_python(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            layout = ExtensionLayout(root / "extensions" / "anima_lora")
            layout.source.mkdir(parents=True)
            layout.train_py.write_text("", encoding="utf-8")
            layout.venv_python.parent.mkdir(parents=True)
            layout.venv_python.write_text("", encoding="utf-8")
            external = root / "external_anima"
            external.mkdir()
            (external / "train.py").write_text("", encoding="utf-8")
            ext_py = external / ".venv" / "Scripts" / "python.exe"
            ext_py.parent.mkdir(parents=True)
            ext_py.write_text("", encoding="utf-8")
            config_path = root / "config" / "anima_fast_backend.toml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                "\n".join(
                    [
                        "[backend]",
                        f'source_dir = "extensions/anima_lora/source"',
                        f'venv_python = "extensions/anima_lora/.venv/Scripts/python.exe"',
                        f'external_root = "{external.as_posix()}"',
                        f'external_python = "{ext_py.as_posix()}"',
                    ]
                ),
                encoding="utf-8",
            )
            runtime = discover_runtime(lora_next_root=root)

        self.assertEqual(runtime.python, layout.venv_python)

    def test_discover_runtime_keeps_linux_uv_venv_launcher_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            layout = ExtensionLayout(root / "extensions" / "anima_lora")
            base_python = root / ".python" / "cpython-3.13.13-linux-x86_64-gnu" / "bin" / "python3.13"
            base_python.parent.mkdir(parents=True)
            base_python.write_text("", encoding="utf-8")

            with mock.patch("mikazuki.anima_fast_backend.settings.sys.platform", "linux"), \
                mock.patch("mikazuki.anima_fast_backend.extension_state.sys.platform", "linux"):
                layout.source.mkdir(parents=True)
                layout.train_py.write_text("", encoding="utf-8")
                layout.venv_python.parent.mkdir(parents=True)
                layout.venv_python.write_text("", encoding="utf-8")
                original_resolve = Path.resolve

                def fake_resolve(path: Path, *args, **kwargs):
                    if path == layout.venv_python:
                        return base_python
                    return original_resolve(path, *args, **kwargs)

                with mock.patch("pathlib.Path.resolve", fake_resolve):
                    runtime = discover_runtime(lora_next_root=root)

                expected = layout.venv_python

        self.assertEqual(runtime.python, expected)
        self.assertIn(".venv", runtime.python.parts)
        self.assertNotEqual(runtime.python, base_python)

    def test_install_starts_background_task_and_returns_log_stream(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "anima"
            source.mkdir()
            (source / "train.py").write_text("", encoding="utf-8")

            with mock.patch("mikazuki.app.api.Path.cwd", return_value=root), \
                mock.patch(
                    "mikazuki.app.api.start_install_task",
                    return_value=("task-1", {"task_id": "task-1", "log_stream": "/api/plugins/anima-lora/install/log/stream/task-1"}),
                ) as starter:
                response = asyncio.run(api.anima_lora_plugin_install(make_request({"source_root": str(source), "dry_run": False})))

        self.assertEqual(response.status, "success")
        self.assertEqual(response.data["task_id"], "task-1")
        self.assertIn("/install/log/stream/task-1", response.data["log_stream"])
        starter.assert_called_once()

    def test_run_rejects_anima_fast_when_extension_is_not_ready(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with mock.patch("mikazuki.app.api.Path.cwd", return_value=root):
                response = asyncio.run(api.create_toml_file(make_request({"model_train_type": "anima-lora-fast"})))

        self.assertEqual(response.status, "fail")
        self.assertIn("not ready", response.message)

    def test_run_rejects_anima_fast_when_audit_drifts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            layout = ExtensionLayout(root / "extensions" / "anima_lora")
            layout.source.mkdir(parents=True)
            layout.train_py.write_text("", encoding="utf-8")
            layout.venv_python.parent.mkdir(parents=True)
            layout.venv_python.write_text("", encoding="utf-8")
            write_install_state(layout, STATE_READY, {"audit": {"ok": True}})

            with mock.patch("mikazuki.app.api.Path.cwd", return_value=root), \
                mock.patch(
                    "mikazuki.app.api.audit_environment",
                    return_value=type("Result", (), {"ok": False, "errors": ["main: torch drift"], "as_dict": lambda self: {"ok": False, "errors": self.errors}})(),
                ):
                response = asyncio.run(api.create_toml_file(make_request({"model_train_type": "anima-lora-fast"})))

        self.assertEqual(response.status, "fail")
        self.assertIn("drift", response.message)

    def test_run_allows_anima_fast_only_after_ready_and_audit_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            layout = ExtensionLayout(root / "extensions" / "anima_lora")
            layout.source.mkdir(parents=True)
            layout.train_py.write_text("", encoding="utf-8")
            layout.venv_python.parent.mkdir(parents=True)
            layout.venv_python.write_text("", encoding="utf-8")
            write_install_state(layout, STATE_READY, {"audit": {"ok": True}})

            adapted = type(
                "Adapted",
                (),
                {
                    "values": {
                        "progress_jsonl": str(root / "logs" / "run.progress.jsonl"),
                        "output_dir": str(root / "output" / "anima_fast"),
                        "logging_dir": str(root / "logs" / "anima_fast"),
                    },
                    "warnings": [],
                },
            )()
            prepared = type(
                "Prepared",
                (),
                {
                    "adapted": adapted,
                    "warnings": [],
                    "auto_resized": False,
                },
            )()
            preflight = type("Preflight", (), {"ok": True, "warnings": [], "as_dict": lambda self: {"ok": True}})()
            audit = type("Audit", (), {"ok": True, "errors": [], "as_dict": lambda self: {"ok": True}})()

            with mock.patch("mikazuki.app.api.Path.cwd", return_value=root), \
                mock.patch("mikazuki.app.api.audit_environment", return_value=audit), \
                mock.patch("mikazuki.app.api.prepare_anima_fast_dataset", return_value=prepared), \
                mock.patch("mikazuki.app.api.run_preflight", return_value=preflight), \
                mock.patch("mikazuki.app.api.process.run_anima_fast_train", return_value=api.APIResponseSuccess(data={"task_id": "train-1"})) as runner:
                response = asyncio.run(api.create_toml_file(make_request({"model_train_type": "anima-lora-fast"})))

        self.assertEqual(response.status, "success")
        self.assertEqual(response.data["task_id"], "train-1")
        runner.assert_called_once()

    def test_preflight_response_includes_adapter_warnings(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            adapted = type(
                "Adapted",
                (),
                {
                    "values": {"attn_mode": "torch"},
                    "warnings": ["cache 与 skip_cache_check 已自动关闭"],
                },
            )()
            preflight = PreflightResult(ok=True, warnings=["runtime warning"])

            with mock.patch("mikazuki.app.api.Path.cwd", return_value=root), \
                mock.patch("mikazuki.app.api._anima_fast_runtime", return_value=object()), \
                mock.patch("mikazuki.app.api.apply_anima_fast_preview", return_value=[]), \
                mock.patch("mikazuki.app.api.adapt_config", return_value=adapted), \
                mock.patch("mikazuki.app.api.run_preflight", return_value=preflight):
                response = asyncio.run(api.anima_lora_plugin_preflight(make_request({"model_train_type": "anima-lora-fast"})))

        self.assertEqual(response.status, "success")
        self.assertIn("cache 与 skip_cache_check 已自动关闭", response.data["warnings"])
        self.assertIn("runtime warning", response.data["warnings"])


if __name__ == "__main__":
    unittest.main()

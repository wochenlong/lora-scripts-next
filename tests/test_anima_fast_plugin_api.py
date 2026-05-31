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


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

if "psutil" not in sys.modules:
    sys.modules["psutil"] = types.ModuleType("psutil")

stub_interrogator = types.ModuleType("mikazuki.tagger.interrogator")
stub_interrogator.available_interrogators = {}
stub_jobs = types.ModuleType("mikazuki.tagger.jobs")
stub_jobs.run_interrogate_job = lambda *args, **kwargs: None
stub_jobs.run_prefetch_job = lambda *args, **kwargs: None
stub_progress = types.ModuleType("mikazuki.tagger.progress")
stub_progress.tagger_progress = types.SimpleNamespace(
    get=lambda: {},
    request_cancel=lambda: False,
    is_busy=lambda: False,
    reset_idle=lambda message=None: None,
)
sys.modules["mikazuki.tagger.interrogator"] = stub_interrogator
sys.modules["mikazuki.tagger.jobs"] = stub_jobs
sys.modules["mikazuki.tagger.progress"] = stub_progress

from starlette.requests import Request

from mikazuki.tasks import TaskManager, TaskStatus
from mikazuki.train_log_hub import hub
from mikazuki.app import api


def make_request(payload: dict) -> Request:
    body = json.dumps(payload).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": "POST", "path": "/api/tasks/purge", "headers": []}, receive)


def _finished_task(tm: TaskManager, task_id: str, finished_at: float):
    task = tm.create_task([sys.executable, "-c", "pass"], dict(os.environ), task_id=task_id)
    task.status = TaskStatus.FINISHED
    task.metadata["finished_at"] = finished_at
    return task


class TaskManagerMaintenanceTests(unittest.TestCase):
    def test_delete_terminal_task(self):
        tm = TaskManager()
        _finished_task(tm, "done", 1.0)
        hub.start_task("done")

        self.assertTrue(tm.delete_task("done"))
        self.assertNotIn("done", tm.tasks)
        self.assertEqual(hub.tail("done"), [])

    def test_delete_refuses_active_task(self):
        tm = TaskManager()
        task = tm.create_task([sys.executable, "-c", "pass"], dict(os.environ), task_id="queued")
        task.status = TaskStatus.QUEUED

        self.assertFalse(tm.delete_task("queued"))
        self.assertIn("queued", tm.tasks)
        self.assertFalse(tm.delete_task("missing"))

    def test_purge_keeps_most_recent(self):
        tm = TaskManager()
        for i in range(5):
            _finished_task(tm, f"t{i}", float(i))
        active = tm.create_task([sys.executable, "-c", "pass"], dict(os.environ), task_id="active")
        active.status = TaskStatus.QUEUED

        removed = tm.purge_tasks(keep_last=2)

        self.assertEqual(removed, 3)
        self.assertEqual(sorted(tm.tasks), ["active", "t3", "t4"])

    def test_purge_all_terminal(self):
        tm = TaskManager()
        _finished_task(tm, "a", 1.0)
        _finished_task(tm, "b", 2.0)

        self.assertEqual(tm.purge_tasks(), 2)
        self.assertEqual(tm.tasks, {})


class TaskMaintenanceApiTests(unittest.TestCase):
    def setUp(self):
        self._created: list[str] = []

    def tearDown(self):
        for task_id in self._created:
            api.tm.tasks.pop(task_id, None)
            hub.drop_task(task_id)

    def _api_task(self, task_id: str, metadata: dict | None = None, status=TaskStatus.FINISHED):
        task = api.tm.create_task([sys.executable, "-c", "pass"], dict(os.environ),
                                  task_id=task_id, metadata=metadata or {})
        task.status = status
        self._created.append(task_id)
        return task

    def test_delete_endpoint(self):
        self._api_task("api-del")
        response = asyncio.run(api.delete_task("api-del"))
        self.assertEqual(response.status, "success")
        self.assertNotIn("api-del", api.tm.tasks)

    def test_delete_endpoint_refuses_active(self):
        self._api_task("api-active", status=TaskStatus.RUNNING)
        response = asyncio.run(api.delete_task("api-active"))
        self.assertEqual(response.status, "fail")
        self.assertIn("api-active", api.tm.tasks)

    def test_purge_endpoint(self):
        # Other suites may leave terminal tasks in the global tm; count them
        # so the assertion stays valid under a full-suite run, and restore any
        # survivors afterwards to avoid disturbing later tests.
        baseline_terminal = {
            tid: task for tid, task in api.tm.tasks.items()
            if task.status in TaskManager._TERMINAL_STATUSES
        }
        self._api_task("api-p1", metadata={"finished_at": 1.0})
        # Far-future timestamp guarantees api-p2 survives keep_last=1 even when
        # other suites left terminal tasks stamped with the real current time.
        self._api_task("api-p2", metadata={"finished_at": time.time() + 3600})
        try:
            response = asyncio.run(api.purge_tasks(make_request({"keep_last": 1})))
            self.assertEqual(response.status, "success")
            self.assertEqual(response.data["removed"], len(baseline_terminal) + 1)
            self.assertNotIn("api-p1", api.tm.tasks)
            self.assertIn("api-p2", api.tm.tasks)
        finally:
            for tid, task in baseline_terminal.items():
                api.tm.tasks.setdefault(tid, task)

    def test_purge_endpoint_rejects_bad_keep_last(self):
        response = asyncio.run(api.purge_tasks(make_request({"keep_last": -1})))
        self.assertEqual(response.status, "fail")
        response = asyncio.run(api.purge_tasks(make_request({"keep_last": "3"})))
        self.assertEqual(response.status, "fail")

    def test_task_config_injects_train_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "task.toml"
            config_path.write_text('output_name = "demo"\nnetwork_dim = 32\n', encoding="utf-8")
            self._api_task("api-cfg", metadata={
                "config_path": str(config_path),
                "backend": "standard",
                "trainer_file": "./scripts/stable/train_network.py",
            })

            response = asyncio.run(api.task_config("api-cfg"))

        self.assertEqual(response.status, "success")
        self.assertEqual(response.data["train_type"], "sd-lora")
        self.assertEqual(response.data["config"]["model_train_type"], "sd-lora")
        self.assertEqual(response.data["config"]["network_dim"], 32)

    def test_task_config_missing_file(self):
        self._api_task("api-cfg-missing", metadata={
            "config_path": "/nonexistent/path/task.toml",
            "backend": "standard",
        })
        response = asyncio.run(api.task_config("api-cfg-missing"))
        self.assertEqual(response.status, "fail")
        self.assertIn("不存在", response.message)

    def test_task_config_musubi_train_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "task.toml"
            config_path.write_text('output_name = "demo"\n', encoding="utf-8")
            self._api_task("api-cfg-musubi", metadata={
                "config_path": str(config_path),
                "backend": "musubi",
            })
            response = asyncio.run(api.task_config("api-cfg-musubi"))

        self.assertEqual(response.status, "success")
        self.assertEqual(response.data["train_type"], "krea2-lora")


if __name__ == "__main__":
    unittest.main()

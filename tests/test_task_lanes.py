from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

if "psutil" not in sys.modules:
    import types
    sys.modules["psutil"] = types.ModuleType("psutil")

from mikazuki.tasks import LANE_MAINTENANCE, TaskManager, TaskStatus


def _wait_status(task, statuses, timeout=30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if task.status in statuses:
            return True
        time.sleep(0.05)
    return False


def _sleeper(seconds=0.5):
    return [sys.executable, "-c", f"import time; time.sleep({seconds})"]


class ComputeLaneQueueTests(unittest.TestCase):
    def test_second_compute_task_is_queued_then_promoted(self):
        tm = TaskManager()
        a = tm.create_task(_sleeper(0.8), dict(os.environ), task_id="a")
        tm.submit(a)
        b = tm.create_task([sys.executable, "-c", "pass"], dict(os.environ), task_id="b")

        self.assertEqual(b.status, TaskStatus.QUEUED)
        tm.submit(b)
        self.assertEqual(tm.queue_position("b"), 1)

        self.assertTrue(_wait_status(b, {TaskStatus.FINISHED}))
        self.assertEqual(a.status, TaskStatus.FINISHED)

    def test_terminate_queued_task_prevents_execution(self):
        tm = TaskManager()
        a = tm.create_task(_sleeper(0.8), dict(os.environ), task_id="a")
        tm.submit(a)
        b = tm.create_task([sys.executable, "-c", "pass"], dict(os.environ), task_id="b")
        tm.submit(b)

        tm.terminate_task("b")

        self.assertEqual(b.status, TaskStatus.TERMINATED)
        self.assertIsNone(tm.queue_position("b"))
        self.assertTrue(_wait_status(a, {TaskStatus.FINISHED}))
        time.sleep(0.3)
        self.assertFalse(hasattr(b, "process"))
        self.assertEqual(b.status, TaskStatus.TERMINATED)

    def test_group_failure_skips_pending_members(self):
        tm = TaskManager()
        fail = tm.create_task(
            [sys.executable, "-c", "import sys; sys.exit(3)"], dict(os.environ),
            task_id="g-1", group="g",
            metadata={"stage": "cache_latents", "stage_label": "缓存图像 latents"},
        )
        t2 = tm.create_task([sys.executable, "-c", "pass"], dict(os.environ),
                            task_id="g-2", group="g", metadata={"stage": "cache_text_encoder"})
        t3 = tm.create_task([sys.executable, "-c", "pass"], dict(os.environ),
                            task_id="g-3", group="g", metadata={"stage": "train"})
        tm.submit_group([fail, t2, t3])

        self.assertTrue(_wait_status(fail, {TaskStatus.FAILED}))
        self.assertTrue(_wait_status(t3, {TaskStatus.FAILED}))
        self.assertEqual(t2.status, TaskStatus.FAILED)
        self.assertIn("已跳过", t2.metadata.get("error", ""))
        self.assertIn("已跳过", t3.metadata.get("error", ""))
        self.assertFalse(hasattr(t2, "process"))

    def test_maintenance_lane_runs_parallel_to_compute(self):
        tm = TaskManager()
        a = tm.create_task(_sleeper(0.8), dict(os.environ), task_id="a")
        tm.submit(a)
        m = tm.create_task(["noop-install"], dict(os.environ),
                           task_id="m-1", lane=LANE_MAINTENANCE,
                           metadata={"kind": "musubi_install"})

        self.assertEqual(m.status, TaskStatus.CREATED)  # never queued by compute load
        m.start_log_only()
        self.assertEqual(m.status, TaskStatus.RUNNING)
        m.finish_log_only(0)
        self.assertEqual(m.status, TaskStatus.FINISHED)
        self.assertTrue(_wait_status(a, {TaskStatus.FINISHED}))

    def test_dump_includes_lane_and_queue_position(self):
        tm = TaskManager()
        a = tm.create_task(_sleeper(0.8), dict(os.environ), task_id="a")
        tm.submit(a)
        b = tm.create_task([sys.executable, "-c", "pass"], dict(os.environ), task_id="b")
        tm.submit(b)

        dump = {entry["id"]: entry for entry in tm.dump()}
        self.assertEqual(dump["a"]["lane"], "compute")
        self.assertEqual(dump["b"]["queue_position"], 1)
        self.assertTrue(_wait_status(b, {TaskStatus.FINISHED}))


class QueuePersistenceTests(unittest.TestCase):
    def test_env_record_filters_sensitive_keys(self):
        tm = TaskManager()
        task = tm.create_task(
            ["noop"], {"HF_TOKEN": "secret-value", "NORMAL": "ok", "PATH": "x"},
            task_id="sensitive", lane=LANE_MAINTENANCE,
        )
        record = tm._task_record(task)
        self.assertNotIn("HF_TOKEN", record["env"])
        self.assertEqual(record["env"]["NORMAL"], "ok")

    def test_queued_task_survives_restore(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "task_queue.json"
            tm1 = TaskManager(persist_path=path)
            a = tm1.create_task(_sleeper(0.8), dict(os.environ), task_id="a")
            tm1.submit(a)
            b = tm1.create_task([sys.executable, "-c", "pass"], dict(os.environ), task_id="b")
            tm1.submit(b)

            self.assertTrue(path.is_file())
            self.assertTrue(_wait_status(a, {TaskStatus.RUNNING}))
            time.sleep(0.2)  # allow post-execute persist to land
            payload = {r["task_id"]: r for r in json.loads(path.read_text(encoding="utf-8"))}
            self.assertIn("b", payload)
            self.assertEqual(payload["a"]["status"], "RUNNING")

            # Simulate restart while "a" is still running and "b" still queued,
            # using the real startup sequence (enable_persistence must not wipe
            # the file before restore_queue reads it).
            tm2 = TaskManager()
            tm2.enable_persistence(path)
            tm2.restore_queue()

            # b is restored into the queue and picked up by tm2's worker at once.
            self.assertIn(tm2.tasks["b"].status, (TaskStatus.QUEUED, TaskStatus.RUNNING))
            interrupted = tm2.tasks.get("a")
            self.assertIsNotNone(interrupted)
            self.assertEqual(interrupted.status, TaskStatus.FAILED)
            self.assertIn("restart", interrupted.metadata.get("error", ""))

            # Restored queue is executable: b should run to completion on tm2's worker.
            self.assertTrue(_wait_status(tm2.tasks["b"], {TaskStatus.FINISHED}))
            self.assertTrue(_wait_status(a, {TaskStatus.FINISHED}))

    def test_restore_corrupt_file_degrades_to_empty(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "task_queue.json"
            path.write_text("{not json", encoding="utf-8")
            tm = TaskManager(persist_path=path)
            tm.restore_queue()  # must not raise
            self.assertEqual(tm.tasks, {})
            self.assertTrue(path.with_suffix(".json.corrupt").is_file())


if __name__ == "__main__":
    unittest.main()

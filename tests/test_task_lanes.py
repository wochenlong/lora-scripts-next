from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_execute_stamps_started_at(self):
        tm = TaskManager()
        task = tm.create_task([sys.executable, "-c", "pass"], dict(os.environ), task_id="s")
        tm.submit(task)
        self.assertTrue(_wait_status(task, {TaskStatus.FINISHED}))
        self.assertGreater(task.metadata.get("started_at", 0), 0)
        self.assertLess(task.metadata["started_at"], task.metadata["finished_at"] + 1)

    def test_retry_strips_started_at(self):
        tm = TaskManager()
        a = tm.create_task([sys.executable, "-c", "pass"], dict(os.environ), task_id="a")
        tm.submit(a)
        self.assertTrue(_wait_status(a, {TaskStatus.FINISHED}))
        old_started = a.metadata["started_at"]

        # Occupy the lane so the retried task stays QUEUED and un-executed.
        blocker = tm.create_task(_sleeper(3), dict(os.environ), task_id="blocker")
        tm.submit(blocker)
        retried = tm.retry_task("a")
        self.assertEqual(retried[0].status, TaskStatus.QUEUED)
        self.assertNotIn("started_at", retried[0].metadata)

        tm.terminate_task("blocker")
        self.assertTrue(_wait_status(retried[0], {TaskStatus.FINISHED}))
        # Re-stamped by execute(), later than the original run.
        self.assertGreaterEqual(retried[0].metadata["started_at"], old_started)


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

    def test_atomic_replace_recovers_from_transient_windows_lock(self):
        """WinError 5 on the queue rename must not silently drop the snapshot.

        Defender / the indexer can hold a momentary handle on the freshly
        written target; _atomic_replace retries briefly and lands the swap.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "task_queue.json.tmp"
            path = Path(td) / "task_queue.json"
            tmp.write_text("[snapshotted]", encoding="utf-8")

            attempts = {"n": 0}
            real_replace = os.replace

            def flaky_replace(src, dst):
                attempts["n"] += 1
                if attempts["n"] <= 2:  # two "Defender is scanning" misses
                    raise PermissionError(5, "Access is denied", str(dst))
                real_replace(src, dst)

            with patch("mikazuki.tasks.os.replace", flaky_replace):
                TaskManager._atomic_replace(tmp, path)
            self.assertEqual(attempts["n"], 3)
            self.assertEqual(path.read_text(encoding="utf-8"), "[snapshotted]")
            self.assertFalse(tmp.exists())

    def test_atomic_replace_exhausts_budget_and_persist_stays_quiet(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "task_queue.json"
            tmp = path.with_name("task_queue.json.tmp")
            tmp.write_text("x", encoding="utf-8")

            def always_locked(src, dst):
                raise PermissionError(5, "Access is denied", str(dst))

            with patch("mikazuki.tasks.os.replace", always_locked):
                with self.assertRaises(PermissionError):
                    TaskManager._atomic_replace(tmp, path)
                # End-to-end: _persist converts the exhausted retry into a
                # warning log, never an exception escaping task submission.
                TaskManager(persist_path=path)._persist()

    def test_queued_task_survives_restore(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "task_queue.json"
            tm1 = TaskManager(persist_path=path)
            # Long sleeper: under full-suite load the persistence assertions
            # below must land well before "a" exits.
            a = tm1.create_task(_sleeper(5), dict(os.environ), task_id="a")
            tm1.submit(a)
            b = tm1.create_task([sys.executable, "-c", "pass"], dict(os.environ), task_id="b")
            tm1.submit(b)

            self.assertTrue(path.is_file())
            self.assertTrue(_wait_status(a, {TaskStatus.RUNNING}))
            # Wait for the post-execute persist to land (a recorded RUNNING).
            deadline = time.time() + 10
            while time.time() < deadline:
                payload = {r["task_id"]: r for r in json.loads(path.read_text(encoding="utf-8"))}
                if payload.get("a", {}).get("status") == "RUNNING" and "b" in payload:
                    break
                time.sleep(0.05)
            self.assertEqual(payload["a"]["status"], "RUNNING")

            # Simulate restart while "a" is still running and "b" still queued,
            # using the real startup sequence (enable_persistence must not wipe
            # the file before restore_queue reads it).
            tm2 = TaskManager()
            tm2.enable_persistence(path)
            tm2.restore_queue()

            # b is restored into the queue but held for manual confirmation.
            self.assertEqual(tm2.tasks["b"].status, TaskStatus.QUEUED)
            self.assertTrue(tm2.tasks["b"].metadata.get("held"))
            interrupted = tm2.tasks.get("a")
            self.assertIsNotNone(interrupted)
            self.assertEqual(interrupted.status, TaskStatus.FAILED)
            self.assertIn("restart", interrupted.metadata.get("error", ""))

            # After manual resume the restored queue entry runs to completion.
            self.assertTrue(tm2.resume_task("b"))
            self.assertTrue(_wait_status(tm2.tasks["b"], {TaskStatus.FINISHED}))
            tm1.terminate_task("a")  # clean up the long sleeper
            self.assertTrue(_wait_status(a, {TaskStatus.TERMINATED}))

    def test_restore_corrupt_file_degrades_to_empty(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "task_queue.json"
            path.write_text("{not json", encoding="utf-8")
            tm = TaskManager(persist_path=path)
            tm.restore_queue()  # must not raise
            self.assertEqual(tm.tasks, {})
            self.assertTrue(path.with_suffix(".json.corrupt").is_file())

    def test_restored_task_is_held_until_resumed(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "task_queue.json"
            tm1 = TaskManager(persist_path=path)
            a = tm1.create_task(_sleeper(0.5), dict(os.environ), task_id="a")
            tm1.submit(a)
            b = tm1.create_task([sys.executable, "-c", "pass"], dict(os.environ), task_id="b")
            tm1.submit(b)
            self.assertTrue(_wait_status(a, {TaskStatus.RUNNING}))

            tm2 = TaskManager()
            tm2.enable_persistence(path)
            tm2.restore_queue()
            restored = tm2.tasks["b"]

            self.assertTrue(restored.metadata.get("held"))
            time.sleep(1.0)  # worker must not pick up held tasks
            self.assertEqual(restored.status, TaskStatus.QUEUED)
            self.assertFalse(hasattr(restored, "process"))

            self.assertTrue(tm2.resume_task("b"))
            self.assertNotIn("held", restored.metadata)
            self.assertTrue(_wait_status(restored, {TaskStatus.FINISHED}))

            self.assertFalse(tm2.resume_task("b"))  # no longer held


class RetryTests(unittest.TestCase):
    def test_retry_finished_task_requeues_clean_copy(self):
        tm = TaskManager()
        a = tm.create_task([sys.executable, "-c", "pass"], dict(os.environ),
                           task_id="a", metadata={"output_name": "x"})
        tm.submit(a)
        self.assertTrue(_wait_status(a, {TaskStatus.FINISHED}))

        retried = tm.retry_task("a")

        self.assertIsNotNone(retried)
        new_task = retried[0]
        self.assertNotEqual(new_task.task_id, "a")
        self.assertEqual(new_task.metadata["retry_of"], "a")
        self.assertNotIn("returncode", new_task.metadata)
        self.assertTrue(_wait_status(new_task, {TaskStatus.FINISHED}))

    def test_retry_rebuilds_stage_group_in_order(self):
        tm = TaskManager()
        stages = ["cache_latents", "cache_text_encoder", "train"]
        old = [
            tm.create_task([sys.executable, "-c", "pass"], dict(os.environ),
                           task_id=f"g-{stage}", group="g",
                           metadata={"stage": stage, "train_task_id": "g"})
            for stage in stages
        ]
        tm.submit_group(old)
        for task in old:
            self.assertTrue(_wait_status(task, {TaskStatus.FINISHED}))

        retried = tm.retry_task("g-train")

        self.assertEqual(len(retried), 3)
        self.assertEqual([t.metadata["stage"] for t in retried], stages)
        new_group = retried[0].group
        self.assertTrue(new_group and new_group != "g")
        self.assertTrue(all(t.group == new_group for t in retried))
        self.assertTrue(all(t.metadata["train_task_id"] == new_group for t in retried))
        for task in retried:
            self.assertTrue(_wait_status(task, {TaskStatus.FINISHED}))

    def test_retry_rejects_running_and_maintenance(self):
        tm = TaskManager()
        running = tm.create_task(_sleeper(0.8), dict(os.environ), task_id="r")
        tm.submit(running)
        self.assertTrue(_wait_status(running, {TaskStatus.RUNNING}))
        self.assertIsNone(tm.retry_task("r"))

        m = tm.create_task(["noop"], dict(os.environ), task_id="m", lane=LANE_MAINTENANCE)
        m.start_log_only()
        m.finish_log_only(1, "boom")
        self.assertIsNone(tm.retry_task("m"))
        self.assertTrue(_wait_status(running, {TaskStatus.FINISHED}))

    def test_retry_interrupted_task_keeps_stored_env(self):
        # Regression: restored RUNNING->FAILED tasks must carry the persisted
        # env (training needs PYTHONPATH to import mikazuki, issue #158).
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "task_queue.json"
            path.write_text(json.dumps([{
                "task_id": "dead",
                "lane": "compute",
                "group": None,
                "command": [sys.executable, "-c", "pass"],
                "cwd": None,
                "metadata": {"backend": "standard"},
                "env": {"PYTHONPATH": "/srv/project"},
                "status": "RUNNING",
            }]), encoding="utf-8")
            tm = TaskManager(persist_path=path)
            tm.restore_queue()

            self.assertEqual(tm.tasks["dead"].status, TaskStatus.FAILED)
            retried = tm.retry_task("dead")

            self.assertIsNotNone(retried)
            self.assertEqual(retried[0].environ["PYTHONPATH"], "/srv/project")


if __name__ == "__main__":
    unittest.main()

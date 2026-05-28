from __future__ import annotations

import unittest
import sys
import types

if "psutil" not in sys.modules:
    sys.modules["psutil"] = types.ModuleType("psutil")

from mikazuki.tasks import TaskManager
from mikazuki.tasks import TaskStatus


class AnimaFastTaskMetadataTests(unittest.TestCase):
    def test_create_task_preserves_metadata_and_cwd_in_dump(self):
        tm = TaskManager()
        task = tm.create_task(
            ["python", "--version"],
            {},
            metadata={"backend": "anima-lora-fast", "progress_jsonl": "logs/anima_fast/t.progress.jsonl"},
            cwd="E:/OpenSourceTeamWork/anima_lora",
            task_id="task-1",
        )

        self.assertIsNotNone(task)
        self.assertEqual(task.cwd, "E:/OpenSourceTeamWork/anima_lora")
        self.assertEqual(tm.dump()[0]["metadata"]["backend"], "anima-lora-fast")
        self.assertEqual(tm.dump()[0]["id"], "task-1")

    def test_wait_does_not_overwrite_terminated_status(self):
        tm = TaskManager()
        task = tm.create_task(["python", "--version"], {}, task_id="task-1")

        class Process:
            def wait(self):
                return 0

        task.process = Process()
        task.status = TaskStatus.TERMINATED
        task.wait()

        self.assertEqual(task.status, TaskStatus.TERMINATED)

    def test_wait_marks_nonzero_exit_as_failed(self):
        tm = TaskManager()
        task = tm.create_task(["python", "--version"], {}, task_id="task-1")

        class Process:
            def wait(self):
                return 1

        task.process = Process()
        task.status = TaskStatus.RUNNING
        task.wait()

        self.assertEqual(task.status, TaskStatus.FAILED)
        self.assertEqual(task.returncode, 1)
        self.assertEqual(task.metadata["returncode"], 1)
        self.assertEqual(tm.dump()[0]["status"], "FAILED")
        self.assertEqual(tm.dump()[0]["returncode"], 1)

    def test_wait_marks_zero_exit_as_finished(self):
        tm = TaskManager()
        task = tm.create_task(["python", "--version"], {}, task_id="task-1")

        class Process:
            def wait(self):
                return 0

        task.process = Process()
        task.status = TaskStatus.RUNNING
        task.wait()

        self.assertEqual(task.status, TaskStatus.FINISHED)
        self.assertEqual(task.returncode, 0)
        self.assertEqual(task.metadata["returncode"], 0)


if __name__ == "__main__":
    unittest.main()

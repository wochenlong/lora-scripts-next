from __future__ import annotations

import unittest
import sys
import types

if "psutil" not in sys.modules:
    sys.modules["psutil"] = types.ModuleType("psutil")

from mikazuki.tasks import TaskManager
from mikazuki.tasks import TaskStatus
from mikazuki.train_log_hub import hub


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
        hub.start_task("task-1")
        hub.append_line("task-1", "loading model\n")
        hub.append_line("task-1", "RuntimeError: missing checkpoint\n")

        class Process:
            def wait(self):
                return 1

        task.process = Process()
        task.status = TaskStatus.RUNNING
        task.wait()

        self.assertEqual(task.status, TaskStatus.FAILED)
        self.assertEqual(task.returncode, 1)
        self.assertEqual(task.metadata["returncode"], 1)
        self.assertEqual(task.metadata["error"], "Training process exited with code 1")
        self.assertEqual(task.metadata["last_log_lines"], ["loading model", "RuntimeError: missing checkpoint"])
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

    def test_execute_records_nonzero_subprocess_log_tail(self):
        tm = TaskManager()
        task = tm.create_task(
            [
                sys.executable,
                "-c",
                "import sys; print('loading dataset'); print('RuntimeError: synthetic failure'); sys.exit(1)",
            ],
            {},
            metadata={"backend": "standard"},
            task_id="task-exit-1",
        )

        task.execute()
        task.wait()

        self.assertEqual(task.status, TaskStatus.FAILED)
        self.assertEqual(task.returncode, 1)
        self.assertEqual(task.metadata["returncode"], 1)
        self.assertEqual(task.metadata["error"], "Training process exited with code 1")
        self.assertIn("loading dataset", task.metadata["last_log_lines"])
        self.assertIn("RuntimeError: synthetic failure", task.metadata["last_log_lines"])
        self.assertEqual(tm.dump()[0]["metadata"]["last_log_lines"][-1], "RuntimeError: synthetic failure")


if __name__ == "__main__":
    unittest.main()

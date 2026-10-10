from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from mikazuki.tasks import TaskManager
from mikazuki.utils.output_naming import ensure_unique_output_name


NOW = datetime(2026, 10, 8, 23, 1, 5)
STAMP = "08230105"


class FakeTask:
    def __init__(self, status, output_name):
        self.status = status
        self.metadata = {"output_name": output_name}


class FakeTM:
    def __init__(self, tasks):
        self.tasks = {str(i): t for i, t in enumerate(tasks)}


def make_tm(*entries):
    from mikazuki.tasks import TaskStatus

    return FakeTM([FakeTask(status, name) for status, name in entries])


class EnsureUniqueOutputNameTests(unittest.TestCase):
    def test_no_conflict_keeps_name(self):
        from mikazuki.tasks import TaskStatus

        tm = make_tm((TaskStatus.RUNNING, "other"))
        config = {"output_name": "mylora", "output_dir": "/nonexistent-dir-357"}
        self.assertIsNone(ensure_unique_output_name(config, tm, NOW))
        self.assertEqual(config["output_name"], "mylora")

    def test_empty_name_is_untouched(self):
        config = {"output_name": "  "}
        self.assertIsNone(ensure_unique_output_name(config, make_tm(), NOW))

    def test_active_task_collision_renames_with_stamp(self):
        from mikazuki.tasks import TaskStatus

        tm = make_tm((TaskStatus.QUEUED, "mylora"))
        config = {"output_name": "mylora", "output_dir": "/nonexistent-dir-357"}
        self.assertEqual(ensure_unique_output_name(config, tm, NOW), "mylora")
        self.assertEqual(config["output_name"], f"mylora-{STAMP}-0")

    def test_finished_task_does_not_block(self):
        from mikazuki.tasks import TaskStatus

        tm = make_tm((TaskStatus.FINISHED, "mylora"), (TaskStatus.FAILED, "mylora"))
        config = {"output_name": "mylora", "output_dir": "/nonexistent-dir-357"}
        self.assertIsNone(ensure_unique_output_name(config, tm, NOW))

    def test_existing_output_dir_collision(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "mylora").mkdir()
            config = {"output_name": "mylora", "output_dir": td}
            self.assertEqual(ensure_unique_output_name(config, make_tm(), NOW), "mylora")
            self.assertEqual(config["output_name"], f"mylora-{STAMP}-0")

    def test_existing_checkpoint_file_collision(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "mylora.safetensors").write_text("", encoding="utf-8")
            config = {"output_name": "mylora", "output_dir": td}
            self.assertEqual(ensure_unique_output_name(config, make_tm(), NOW), "mylora")
            self.assertEqual(config["output_name"], f"mylora-{STAMP}-0")

    def test_unrelated_prefix_files_do_not_collide(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "mylora-v2.safetensors").write_text("", encoding="utf-8")
            config = {"output_name": "mylora", "output_dir": td}
            self.assertIsNone(ensure_unique_output_name(config, make_tm(), NOW))

    def test_epoch_checkpoint_collision(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "mylora-000003.safetensors").write_text("", encoding="utf-8")
            config = {"output_name": "mylora", "output_dir": td}
            self.assertEqual(ensure_unique_output_name(config, make_tm(), NOW), "mylora")

    def test_step_checkpoint_collision(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "mylora-step00001000.safetensors").write_text("", encoding="utf-8")
            config = {"output_name": "mylora", "output_dir": td}
            self.assertEqual(ensure_unique_output_name(config, make_tm(), NOW), "mylora")

    def test_optimizer_state_dir_collision(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "mylora-000002-state").mkdir()
            config = {"output_name": "mylora", "output_dir": td}
            self.assertEqual(ensure_unique_output_name(config, make_tm(), NOW), "mylora")

    def test_case_insensitive_on_windows(self):
        from unittest import mock

        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "MyLora.safetensors").write_text("", encoding="utf-8")
            config = {"output_name": "mylora", "output_dir": td}
            with mock.patch("mikazuki.utils.output_naming.sys") as fake_sys:
                fake_sys.platform = "win32"
                self.assertEqual(ensure_unique_output_name(config, make_tm(), NOW), "mylora")

    def test_case_sensitive_elsewhere(self):
        import sys as real_sys
        from unittest import mock

        if real_sys.platform == "win32":
            self.skipTest("case sensitivity only applies off Windows")
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "MyLora.safetensors").write_text("", encoding="utf-8")
            config = {"output_name": "mylora", "output_dir": td}
            with mock.patch("mikazuki.utils.output_naming.sys") as fake_sys:
                fake_sys.platform = "linux"
                self.assertIsNone(ensure_unique_output_name(config, make_tm(), NOW))

    def test_digit_cycles_until_free(self):
        from mikazuki.tasks import TaskStatus

        tm = make_tm(
            (TaskStatus.RUNNING, "mylora"),
            (TaskStatus.QUEUED, f"mylora-{STAMP}-0"),
            (TaskStatus.QUEUED, f"mylora-{STAMP}-1"),
        )
        config = {"output_name": "mylora", "output_dir": "/nonexistent-dir-357"}
        ensure_unique_output_name(config, tm, NOW)
        self.assertEqual(config["output_name"], f"mylora-{STAMP}-2")

    def test_all_digits_taken_falls_back_to_uuid_suffix(self):
        from mikazuki.tasks import TaskStatus

        tm = make_tm(
            (TaskStatus.RUNNING, "mylora"),
            *[(TaskStatus.QUEUED, f"mylora-{STAMP}-{d}") for d in range(10)],
        )
        config = {"output_name": "mylora", "output_dir": "/nonexistent-dir-357"}
        ensure_unique_output_name(config, tm, NOW)
        self.assertRegex(config["output_name"], rf"^mylora-{STAMP}-[0-9a-f]{{4}}$")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from mikazuki.train_log_hub import TrainLogHub, strip_ansi


class TrainLogHubAnsiTests(unittest.TestCase):
    def test_strip_ansi_removes_colors_progress_and_hyperlinks(self):
        raw = (
            "\x1b[2;36m2026-06-05 15:21:06\x1b[0m "
            "\x1b[34mINFO\x1b[0m "
            "\x1b]8;;file:///tmp/train.py\x1b\\train.py\x1b]8;;\x1b\\ "
            "steps: 0%|\x1b[34m \x1b[0m| 0/10"
        )

        self.assertEqual(
            strip_ansi(raw),
            "2026-06-05 15:21:06 INFO train.py steps: 0%| | 0/10",
        )

    def test_append_line_buffers_sanitized_text(self):
        hub = TrainLogHub()
        hub.start_task("task-ansi")

        hub.append_line("task-ansi", "\x1b[34mINFO\x1b[0m running training\r\n")
        hub.append_line("task-ansi", "\x1b]8;;file:///tmp/a.py\x1b\\a.py\x1b]8;;\x1b\\\n")

        lines, total, done = hub.snapshot_from("task-ansi", 0)

        self.assertEqual(lines, ["INFO running training", "a.py"])
        self.assertEqual(total, 2)
        self.assertFalse(done)

    def test_tail_returns_recent_sanitized_lines(self):
        hub = TrainLogHub()
        hub.start_task("task-tail")

        hub.append_line("task-tail", "\x1b[31mfirst\x1b[0m\n")
        hub.append_line("task-tail", "second\n")
        hub.append_line("task-tail", "third\n")

        self.assertEqual(hub.tail("task-tail", 2), ["second", "third"])
        self.assertEqual(hub.tail("missing", 2), [])


if __name__ == "__main__":
    unittest.main()

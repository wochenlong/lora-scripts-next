from __future__ import annotations

import json
import unittest

from mikazuki.anima_fast_backend.progress import (
    merge_anima_training_metrics,
    metrics_from_anima_events,
)


class AnimaFastProgressMetricsTests(unittest.TestCase):
    def test_step_event_reads_avr_loss_and_epoch(self):
        events = [
            {"ev": "run_start", "total_steps": 20, "total_epochs": 2, "ts": 0},
            {"ev": "step", "global_step": 5, "epoch": 1, "avr_loss": 0.0886, "ts": 50},
        ]
        metrics = metrics_from_anima_events(events)
        self.assertEqual(metrics["step"], 5)
        self.assertEqual(metrics["total_steps"], 20)
        self.assertEqual(metrics["epoch"], "1/2")
        self.assertEqual(metrics["loss"], "0.0886")
        self.assertEqual(metrics["elapsed"], "50秒")
        self.assertIn("eta", metrics)

    def test_step_event_reads_loss_average_key(self):
        events = [
            {"ev": "run_start", "total_steps": 10, "total_epochs": 1},
            {"ev": "step", "global_step": 2, "epoch": 1, "loss/average": 0.12, "ts": 10},
        ]
        metrics = metrics_from_anima_events(events)
        self.assertEqual(metrics["loss"], "0.12")

    def test_merge_prefers_jsonl_loss_when_stdout_missing(self):
        stdout = {"step": 0, "total_steps": 20, "epoch": "1/2", "eta": "?"}
        anima = {
            "step": 5,
            "total_steps": 20,
            "loss": "0.09",
            "epoch": "1/2",
            "elapsed": "1分00秒",
            "eta": "3分00秒",
            "progress_source": "anima_progress_jsonl",
        }
        merged = merge_anima_training_metrics(stdout, anima)
        self.assertEqual(merged["step"], 5)
        self.assertEqual(merged["loss"], "0.09")
        self.assertEqual(merged["eta"], "3分00秒")

    def test_merge_keeps_stdout_eta_when_jsonl_missing(self):
        stdout = {"step": 3, "total_steps": 20, "eta": "02:30", "loss": "0.1"}
        anima = {"step": 3, "total_steps": 20, "loss": "0.11", "progress_source": "anima_progress_jsonl"}
        merged = merge_anima_training_metrics(stdout, anima)
        self.assertEqual(merged["eta"], "02:30")
        self.assertEqual(merged["loss"], "0.11")


if __name__ == "__main__":
    unittest.main()

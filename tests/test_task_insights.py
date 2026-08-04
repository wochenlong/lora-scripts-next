import tempfile
import time
import os
import unittest
from pathlib import Path

from mikazuki.utils import task_insights

try:
    from tensorboard.summary.writer.event_file_writer import EventFileWriter  # noqa: F401
    from torch.utils.tensorboard import SummaryWriter
    HAS_TENSORBOARD = True
except Exception:
    HAS_TENSORBOARD = False


def _write_config(tmp: Path, output_dir: Path, logging_dir: Path, output_name: str = "aki") -> Path:
    config = tmp / "task.toml"
    config.write_text(
        f'output_dir = "{output_dir.as_posix()}"\n'
        f'logging_dir = "{logging_dir.as_posix()}"\n'
        f'output_name = "{output_name}"\n',
        encoding="utf-8",
    )
    return config


class TaskInsightsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.output_dir = self.tmp / "output"
        self.logging_dir = self.tmp / "logs"
        (self.output_dir / "sample").mkdir(parents=True)
        self.logging_dir.mkdir()
        self.metadata = {"config_path": str(_write_config(self.tmp, self.output_dir, self.logging_dir))}

    def tearDown(self):
        self._tmp.cleanup()

    def test_resolve_task_dirs_reads_autosaved_toml(self):
        dirs = task_insights.resolve_task_dirs(self.metadata)
        self.assertEqual(dirs["output_dir"], self.output_dir.resolve())
        self.assertEqual(dirs["logging_dir"], self.logging_dir.resolve())
        self.assertEqual(dirs["output_name"], "aki")

    def test_resolve_task_dirs_missing_config_returns_empty_dirs(self):
        dirs = task_insights.resolve_task_dirs({"config_path": str(self.tmp / "missing.toml")})
        self.assertIsNone(dirs["output_dir"])
        self.assertEqual(dirs["output_name"], "")

    def test_list_preview_images_filters_by_name_and_creation_time(self):
        sample = self.output_dir / "sample"
        keep = sample / "aki_e000002_20260804_120000.png"
        keep.write_bytes(b"png")
        other = sample / "other_e000002_20260804_120000.png"
        other.write_bytes(b"png")
        old = sample / "aki_e000001_20260804_110000.png"
        old.write_bytes(b"png")
        earlier = time.time() - 120
        os.utime(old, (earlier, earlier))

        images = task_insights.list_preview_images(self.metadata)
        self.assertEqual([item["name"] for item in images], [old.name, keep.name])
        self.assertEqual(images[-1]["epoch"], 2)

        self.metadata["created_at"] = time.time() + 60
        self.assertEqual(task_insights.list_preview_images(self.metadata), [])

    def test_list_preview_images_without_output_dir_is_empty(self):
        self.metadata["config_path"] = str(self.tmp / "missing.toml")
        self.assertEqual(task_insights.list_preview_images(self.metadata), [])

    def test_resolve_preview_image_only_serves_scanned_names(self):
        sample = self.output_dir / "sample"
        keep = sample / "aki_e000002_x.png"
        keep.write_bytes(b"png")
        secret = self.tmp / "secret.png"
        secret.write_bytes(b"png")

        self.assertEqual(task_insights.resolve_preview_image(self.metadata, keep.name), keep)
        self.assertIsNone(task_insights.resolve_preview_image(self.metadata, "../secret.png"))
        self.assertIsNone(task_insights.resolve_preview_image(self.metadata, "secret.png"))
        self.assertIsNone(task_insights.resolve_preview_image(self.metadata, "missing.png"))

    def test_downsample_keeps_endpoints_within_limit(self):
        points = [{"step": i, "value": float(i)} for i in range(1200)]
        sampled = task_insights.downsample(points, 500)
        self.assertLessEqual(len(sampled), 501)
        self.assertEqual(sampled[0], points[0])
        self.assertEqual(sampled[-1], points[-1])
        self.assertEqual(task_insights.downsample(points[:10], 500), points[:10])

    def test_parse_step_and_epoch_from_sample_names(self):
        self.assertEqual(task_insights.parse_step("aki_000100_00_20260804103000_2333.png"), 100)
        self.assertIsNone(task_insights.parse_epoch("aki_000100_00_20260804103000_2333.png"))
        self.assertEqual(task_insights.parse_epoch("aki_e000001_00_20260804103000_2333.png"), 1)
        self.assertIsNone(task_insights.parse_step("aki_e000001_00_20260804103000_2333.png"))

    def test_read_progress_parses_tqdm_lines(self):
        lines = [
            "epoch 1/5\n",
            "steps:   0%|          | 0/1000 [00:00<?, ?it/s]\rsteps:  12%|█▏        | 120/1000 [00:30<03:40, 3.99it/s, avr_loss=0.123]",
        ]
        progress = task_insights.read_progress(lines)
        self.assertEqual(progress["percent"], 12)
        self.assertEqual(progress["step"], 120)
        self.assertEqual(progress["total_steps"], 1000)
        self.assertEqual(progress["epoch"], 1)
        self.assertEqual(progress["total_epochs"], 5)

    def test_read_progress_ignores_unrelated_bars(self):
        lines = ["caching latents:  50%|████| 3/6 [00:01<00:01, 2.0it/s]"]
        self.assertEqual(task_insights.read_progress(lines), {})

    def test_read_loss_scalars_without_event_files_is_empty(self):
        self.assertEqual(task_insights.read_loss_scalars(self.metadata), {})

    @unittest.skipUnless(HAS_TENSORBOARD, "tensorboard not available")
    def test_read_loss_scalars_selects_run_started_after_task_creation(self):
        old_run = self.logging_dir / "20260801000000"
        old_writer = SummaryWriter(log_dir=str(old_run))
        old_writer.add_scalar("loss/average", 99.0, 0)
        old_writer.close()

        new_run = self.logging_dir / "20260804120000"
        writer = SummaryWriter(log_dir=str(new_run))
        for step in range(5):
            writer.add_scalar("loss/average", 1.0 / (step + 1), step)
            writer.add_scalar("loss/current", 0.5 / (step + 1), step)
        writer.close()

        tags = task_insights.read_loss_scalars(self.metadata)
        self.assertIn("loss/average", tags)
        self.assertAlmostEqual(tags["loss/average"][-1]["value"], 0.2)

        self.metadata["created_at"] = time.mktime((2026, 8, 2, 0, 0, 0, 0, 0, -1))
        tags = task_insights.read_loss_scalars(self.metadata)
        self.assertAlmostEqual(tags["loss/average"][-1]["value"], 0.2)

        self.metadata["created_at"] = time.time() + 60
        self.assertEqual(task_insights.read_loss_scalars(self.metadata), {})


if __name__ == "__main__":
    unittest.main()

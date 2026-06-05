import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from train_monitor import server


class TrainMonitorStatusTests(unittest.TestCase):
    def test_gui_api_failure_is_non_blocking_warning(self):
        with mock.patch.object(server, "newest_preview_images", return_value=[]), \
                mock.patch.object(server, "_training_output_dir", return_value=None), \
                mock.patch.object(server, "latest_training_config", return_value={}), \
                mock.patch.object(server, "build_model_outputs", return_value={}), \
                mock.patch.object(server, "_extract_train_params", return_value=[]), \
                mock.patch.object(server, "tensorboard_loss_scalars", return_value=[{"tag": "loss/average"}]), \
                mock.patch.object(server, "gpu_info", return_value={}), \
                mock.patch.object(server, "fetch_gui_json", side_effect=OSError("HTTP Error 404: Not Found")):
            status = server.collect_status()

        self.assertNotIn("error", status)
        self.assertIn("gui_warning", status)
        self.assertEqual(status["state"], "GUI 离线")
        self.assertEqual(status["tensorboard_loss"], [{"tag": "loss/average"}])

    def test_infer_model_type_anima_finetune_from_script(self):
        lines = [
            "accelerate launch scripts/dev/anima_train.py --config_file config/autosave/foo.toml",
            "INFO dit device: cuda:0",
        ]
        self.assertEqual(server.infer_model_type(lines), "Anima Finetune")

    def test_infer_model_type_anima_finetune_from_config(self):
        autosave = server.REPO / "config/autosave"
        autosave.mkdir(parents=True, exist_ok=True)
        cfg = autosave / "_unit_test_anima_finetune_monitor.toml"
        try:
            cfg.write_text('model_train_type = "anima-finetune"\n', encoding="utf-8")
            future = time.time() + 7200
            os.utime(cfg, (future, future))
            self.assertEqual(server.infer_model_type(["starting training"]), "Anima Finetune")
        finally:
            cfg.unlink(missing_ok=True)

    def test_infer_model_type_anima_lora_network(self):
        lines = ["python vendor/sd-scripts/anima_train_network.py --config_file x.toml"]
        self.assertEqual(server.infer_model_type(lines), "Anima LoRA")

    def test_anima_fast_progress_jsonl_overrides_stdout_metrics(self):
        with tempfile.TemporaryDirectory() as td:
            progress = Path(td) / "progress.jsonl"
            progress.write_text(
                "\n".join([
                    json.dumps({"ev": "run_start", "total_steps": 10}),
                    json.dumps({"ev": "step", "global_step": 3, "loss": 0.25}),
                ]),
                encoding="utf-8",
            )
            task = {
                "id": "task-1",
                "status": "RUNNING",
                "metadata": {
                    "backend": "anima-lora-fast",
                    "progress_jsonl": str(progress),
                },
            }
            with mock.patch.object(server, "newest_preview_images", return_value=[]), \
                    mock.patch.object(server, "_training_output_dir", return_value=None), \
                    mock.patch.object(server, "latest_training_config", return_value={}), \
                    mock.patch.object(server, "build_model_outputs", return_value={}) as build_outputs, \
                    mock.patch.object(server, "_extract_train_params", return_value=[]), \
                    mock.patch.object(server, "tensorboard_loss_scalars", return_value=[]), \
                    mock.patch.object(server, "gpu_info", return_value={}), \
                    mock.patch.object(server, "gpu_memory_used_mb", return_value=None), \
                    mock.patch.object(server, "fetch_gui_json", return_value=({"status": "success", "data": {"tasks": [task]}}, "http://gui/api")), \
                    mock.patch.object(server, "fetch_json", return_value={"status": "success", "data": {"lines": ["no progress here"], "done": False}}):
                status = server.collect_status()

        self.assertEqual(status["model_type"], "Anima Fast LoRA")
        self.assertEqual(status["metrics"]["step"], 3)
        self.assertEqual(status["metrics"]["total_steps"], 10)
        self.assertEqual(status["metrics"]["progress_source"], "anima_progress_jsonl")
        build_outputs.assert_any_call(None)

    def test_active_task_metadata_output_dir_overrides_latest_config(self):
        task = {
            "id": "task-1",
            "status": "RUNNING",
            "metadata": {
                "backend": "anima-lora-fast",
                "output_dir": "output/anima_fast/run-1",
            },
        }
        with mock.patch.object(server, "newest_preview_images", return_value=[]), \
                mock.patch.object(server, "_training_output_dir", return_value=server.REPO / "output" / "old"), \
                mock.patch.object(server, "latest_training_config", return_value={}), \
                mock.patch.object(server, "build_model_outputs", return_value={"outputs": [], "outputs_primary": [], "outputs_other": []}) as build_outputs, \
                mock.patch.object(server, "_extract_train_params", return_value=[]), \
                mock.patch.object(server, "tensorboard_loss_scalars", return_value=[]), \
                mock.patch.object(server, "gpu_info", return_value={}), \
                mock.patch.object(server, "gpu_memory_used_mb", return_value=None), \
                mock.patch.object(server, "fetch_gui_json", return_value=({"status": "success", "data": {"tasks": [task]}}, "http://gui/api")), \
                mock.patch.object(server, "fetch_json", return_value={"status": "success", "data": {"lines": [], "done": False}}):
            server.collect_status()

        self.assertEqual(build_outputs.call_args_list[-1].args[0], server.REPO / "output" / "anima_fast" / "run-1")

    def test_anima_fast_output_dir_safetensors_are_discoverable(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            output_dir = repo / "output"
            train_out = output_dir / "anima_fast" / "run-1"
            model_file = train_out / "anima-fast-test.safetensors"
            train_out.mkdir(parents=True)
            model_file.write_bytes(b"fake model bytes")

            with mock.patch.object(server, "REPO", repo), \
                    mock.patch.object(server, "OUTPUT_DIR", output_dir):
                outputs = server.build_model_outputs(train_out)
                fallback_outputs = server.build_model_outputs(None)

        self.assertEqual(outputs["output_scope"], "output/anima_fast/run-1")
        self.assertEqual(len(outputs["outputs_primary"]), 1)
        self.assertEqual(outputs["outputs_primary"][0]["path"], str(model_file))
        self.assertEqual(outputs["outputs"][0]["path"], str(model_file))
        self.assertEqual(fallback_outputs["outputs"][0]["path"], str(model_file))

    def test_extract_train_params_uses_source_image_dir_for_anima_fast(self):
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / "10_style"
            data.mkdir()
            (data / "a.png").write_bytes(b"x")
            config = {
                "source_image_dir": str(data),
                "train_batch_size": "1",
                "gradient_accumulation_steps": "1",
                "max_train_epochs": "2",
            }
            params = server._extract_train_params(config)
            labels = [item["label"] for item in params]
            self.assertIn("总步数", labels)

    def test_kohya_step_estimate_ignores_subdirs_without_repeat_prefix(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = root / "dataset"
            valid = data / "10_style"
            ignored = data / "style_misc"
            valid.mkdir(parents=True)
            ignored.mkdir()
            (valid / "a.png").write_bytes(b"x")
            for idx in range(20):
                (ignored / f"ignored_{idx}.png").write_bytes(b"x")

            estimate = server.estimate_training_steps(
                {
                    "train_data_dir": str(data),
                    "train_batch_size": "4",
                    "gradient_accumulation_steps": "1",
                    "max_train_epochs": "2",
                },
                engine="kohya",
            )

        self.assertEqual(estimate["samples_per_epoch"], 10)
        self.assertEqual(estimate["steps_per_epoch"], 3)
        self.assertEqual(estimate["total_steps"], 6)

    def test_kohya_step_detail_lists_each_repeat_folder(self):
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / "dataset"
            first = data / "10_style"
            second = data / "2_closeup"
            first.mkdir(parents=True)
            second.mkdir()
            for idx in range(2):
                (first / f"a{idx}.png").write_bytes(b"x")
            (second / "b.png").write_bytes(b"x")

            estimate = server.estimate_training_steps(
                {
                    "train_data_dir": str(data),
                    "train_batch_size": "4",
                    "gradient_accumulation_steps": "1",
                    "max_train_epochs": "3",
                },
                engine="kohya",
            )

        self.assertEqual(estimate["samples_per_epoch"], 22)
        self.assertEqual(estimate["total_steps"], 18)
        self.assertIn("10_style:2x10r", estimate["detail"])
        self.assertIn("2_closeup:1x2r", estimate["detail"])

    def test_anima_fast_train_params_prefer_runtime_total_steps(self):
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / "1_style"
            data.mkdir()
            (data / "a.png").write_bytes(b"x")
            config = {
                "model_train_type": "anima-lora-fast",
                "source_image_dir": str(data),
                "train_batch_size": "1",
                "gradient_accumulation_steps": "1",
                "max_train_epochs": "100",
            }

            params = server._extract_train_params(
                config,
                engine="anima-fast",
                runtime_metrics={"total_steps": 12, "progress_source": "anima_progress_jsonl"},
            )

        step_card = params[0]
        self.assertTrue(step_card["value"].startswith("12"))
        self.assertIn("Fast", step_card["value"])

    def test_collect_status_uses_anima_fast_runtime_total_steps_for_train_params(self):
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / "1_style"
            data.mkdir()
            (data / "a.png").write_bytes(b"x")
            progress = Path(td) / "progress.jsonl"
            progress.write_text(
                "\n".join([
                    json.dumps({"ev": "run_start", "total_steps": 12, "total_epochs": 2}),
                    json.dumps({"ev": "step", "global_step": 2, "loss": 0.1}),
                ]),
                encoding="utf-8",
            )
            task = {
                "id": "t-fast",
                "status": "RUNNING",
                "metadata": {
                    "backend": "anima-lora-fast",
                    "progress_jsonl": str(progress),
                },
            }

            def fetch_gui_side_effect(path: str):
                if path == "/train/tasks":
                    return {"status": "success", "data": {"tasks": [task]}}, "http://gui/api/train/tasks"
                if path.startswith("/train/log/tail/"):
                    return {"status": "success", "data": {"lines": [], "done": False}}, "http://gui/api/train/log/tail/t-fast"
                raise AssertionError(f"unexpected path: {path}")

            with mock.patch.object(server, "newest_preview_images", return_value=[]), \
                    mock.patch.object(server, "_training_output_dir", return_value=None), \
                    mock.patch.object(server, "latest_training_config", return_value={
                        "model_train_type": "anima-lora-fast",
                        "source_image_dir": str(data),
                        "train_batch_size": "1",
                        "gradient_accumulation_steps": "1",
                        "max_train_epochs": "100",
                    }), \
                    mock.patch.object(server, "build_model_outputs", return_value={}), \
                    mock.patch.object(server, "tensorboard_loss_scalars", return_value=[]), \
                    mock.patch.object(server, "gpu_info", return_value={}), \
                    mock.patch.object(server, "gpu_memory_used_mb", return_value=None), \
                    mock.patch.object(server, "fetch_gui_json", side_effect=fetch_gui_side_effect):
                status = server.collect_status()

        self.assertEqual(status["metrics"]["total_steps"], 12)
        self.assertTrue(status["train_params"][0]["value"].startswith("12"))
        self.assertIn("Fast", status["train_params"][0]["value"])

    def test_newest_preview_images_uses_active_task_output_dir(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            sample_dir = repo / "output" / "lora_demo_run" / "sample"
            sample_dir.mkdir(parents=True)
            image = sample_dir / "lora_demo_run_e000001_00_20260601020605_42.png"
            image.write_bytes(b"png")
            task = {
                "metadata": {
                    "output_dir": "output/lora_demo_run",
                    "output_name": "lora_demo_run",
                }
            }
            with mock.patch.object(server, "REPO", repo), \
                    mock.patch.object(server, "OUTPUT_DIR", repo / "output"), \
                    mock.patch.object(server, "latest_training_config", return_value={
                        "output_dir": "output/other_run",
                        "output_name": "other_run",
                    }):
                preview_dir, preview_name, _ = server._preview_context(task, server.latest_training_config())
                previews = server.newest_preview_images(
                    output_dir=preview_dir,
                    output_name=preview_name,
                )
        self.assertEqual(len(previews), 1)
        self.assertIn("lora_demo_run", previews[0]["name"])

    def test_train_monitor_imports_when_started_from_monitor_dir(self):
        completed = subprocess.run(
            [sys.executable, "-c", "import server; print((server.REPO / 'train_monitor').is_dir())"],
            cwd=Path("train_monitor"),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "True")

    def test_parse_log_anima_finetune_extracts_loss_points(self):
        lines = [
            "steps:  10%|██        | 50/500 [01:23<12:34, avr_loss=0.0823]",
            "steps:  20%|████      | 100/500 [02:46<11:04, avr_loss=0.0712]",
        ]
        metrics = server.parse_log(lines)
        self.assertEqual(metrics["loss"], "0.0712")
        self.assertGreaterEqual(len(metrics["loss_points"]), 2)
        self.assertEqual(metrics["loss_points"][0]["step"], 50)

    def test_tensorboard_scalar_tags_include_anima_finetune_loss(self):
        self.assertIn("loss", server.TENSORBOARD_SCALAR_TAGS)
        self.assertIn("loss/epoch", server.TENSORBOARD_SCALAR_TAGS)

    def test_collect_status_exposes_log_loss_points_without_tensorboard(self):
        log_lines = [
            "accelerate launch scripts/dev/anima_train.py --config_file config/autosave/foo.toml",
            "steps:  10%|██        | 10/100 [00:10<01:30, avr_loss=0.1234]",
        ]

        def fetch_gui_side_effect(path: str):
            if path == "/train/tasks":
                return (
                    {"status": "success", "data": {"tasks": [{"id": "t1", "status": "RUNNING"}]}},
                    "http://gui/api/train/tasks",
                )
            if path.startswith("/train/log/tail/"):
                return (
                    {"status": "success", "data": {"lines": log_lines, "done": False}},
                    "http://gui/api/train/log/tail/t1",
                )
            raise AssertionError(f"unexpected path: {path}")

        with mock.patch.object(server, "newest_preview_images", return_value=[]), \
                mock.patch.object(server, "_training_output_dir", return_value=None), \
                mock.patch.object(server, "latest_training_config", return_value={"model_train_type": "anima-finetune"}), \
                mock.patch.object(server, "build_model_outputs", return_value={}), \
                mock.patch.object(server, "_extract_train_params", return_value=[]), \
                mock.patch.object(server, "tensorboard_loss_scalars", return_value=[]), \
                mock.patch.object(server, "gpu_info", return_value={}), \
                mock.patch.object(server, "gpu_memory_used_mb", return_value=None), \
                mock.patch.object(server, "fetch_gui_json", side_effect=fetch_gui_side_effect):
            status = server.collect_status()

        self.assertEqual(status["model_type"], "Anima Finetune")
        self.assertGreaterEqual(len(status["metrics"]["loss_points"]), 1)
        self.assertEqual(status["tensorboard_loss"], [])


if __name__ == "__main__":
    unittest.main()

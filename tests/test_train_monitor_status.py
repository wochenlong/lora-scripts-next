import os
import time
import unittest
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


if __name__ == "__main__":
    unittest.main()

import os
import unittest
from pathlib import Path
from unittest import mock

from mikazuki.spa import (
    should_fallback_to_spa,
    train_monitor_browser_url,
    train_monitor_enabled,
    train_monitor_url,
    wait_for_tcp_port,
)


ROOT = Path(__file__).resolve().parents[1]
ROUTES = (
    "training",
    "dataset",
    "dataset/editor",
    "dataset/tagger",
    "tasks",
    "settings",
    "settings/ui",
    "settings/engines",
    "settings/about",
    "settings/changelog",
    "settings/plugins/sample-plugin",
    "plugins/sample-plugin/artifacts/sample-artifact",
    "lora/basic.html",
    "lora/master.html",
    "lora/flux.html",
    "lora/sd3.html",
    "lora/anima-fast.html",
    "lora/anima-finetune.html",
    "dreambooth/index.html",
    "tagger.html",
    "native-tageditor.html",
    "dataset-editor.html",
    "tensorboard.html",
    "task.html",
    "other/settings.html",
    "help/guide.html",
    "unknown/client/route",
)


class VueSpaRouteTests(unittest.TestCase):
    def test_train_monitor_redirect_uses_request_host_and_runtime_port(self):
        self.assertEqual(train_monitor_url("http://192.168.1.20:28000/train-monitor", 6012), "http://192.168.1.20:6012/")
        self.assertEqual(train_monitor_url("https://trainer.example.com/train-monitor", 6008), "http://trainer.example.com:6008/")
        self.assertEqual(train_monitor_url("http://[::1]:28000/train-monitor", 6008), "http://[::1]:6008/")

    def test_all_history_routes_use_spa_fallback(self):
        self.assertTrue((ROOT / "frontend/dist/index.html").is_file())
        for route in ROUTES:
            self.assertTrue(should_fallback_to_spa(route, 404), route)

    def test_static_resources_never_use_spa_fallback(self):
        for path in ("assets/missing.js", "assets/missing.css", "font-roboto/missing.woff2", "favicon.ico"):
            self.assertFalse(should_fallback_to_spa(path, 404), path)

    def test_non_404_responses_never_use_spa_fallback(self):
        for status in (200, 301, 403, 500):
            self.assertFalse(should_fallback_to_spa("lora/basic.html", status), status)

    def test_application_uses_the_tested_fallback_policy(self):
        source = (ROOT / "mikazuki/app/application.py").read_text(encoding="utf-8")
        self.assertIn("should_fallback_to_spa(path, ex.status_code)", source)

    def test_gui_passes_its_final_host_to_train_monitor(self):
        source = (ROOT / "gui.py").read_text(encoding="utf-8")
        listen = source.index('if args.listen:')
        monitor_host = source.index('os.environ["TRAIN_MONITOR_HOST"] = args.host')
        self.assertLess(listen, monitor_host)
        self.assertIn('TRAIN_MONITOR_ENABLED', source)

    def test_train_monitor_browser_url_requires_enabled_flag(self):
        with mock.patch.dict(os.environ, {"TRAIN_MONITOR_ENABLED": "0", "TRAIN_MONITOR_PORT": "6008"}, clear=False):
            self.assertFalse(train_monitor_enabled())
            self.assertIsNone(train_monitor_browser_url())
        with mock.patch.dict(
            os.environ,
            {
                "TRAIN_MONITOR_ENABLED": "1",
                "TRAIN_MONITOR_HOST": "0.0.0.0",
                "TRAIN_MONITOR_PORT": "6012",
            },
            clear=False,
        ):
            self.assertTrue(train_monitor_enabled())
            self.assertEqual(train_monitor_browser_url(), "http://127.0.0.1:6012/")

    def test_wait_for_tcp_port_times_out_on_closed_port(self):
        self.assertFalse(wait_for_tcp_port("127.0.0.1", 1, timeout=0.3, interval=0.1))

    def test_application_gates_monitor_browser_open(self):
        source = (ROOT / "mikazuki/app/application.py").read_text(encoding="utf-8")
        self.assertIn("train_monitor_browser_url()", source)
        self.assertIn("wait_for_tcp_port", source)
        self.assertNotIn('browser.open(f\'http://127.0.0.1:{monitor_port}\')', source)


if __name__ == "__main__":
    unittest.main()

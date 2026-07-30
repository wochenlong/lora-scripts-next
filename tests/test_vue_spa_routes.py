import unittest
from pathlib import Path

from mikazuki.spa import should_fallback_to_spa, train_monitor_url


ROOT = Path(__file__).resolve().parents[1]
ROUTES = (
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


if __name__ == "__main__":
    unittest.main()

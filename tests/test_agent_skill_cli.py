"""Tests for the next-trainer agent skill CLI (.opencode/skills/next-trainer/scripts/nt.py).

End-to-end against a stub HTTP server (stdlib http.server in a thread), so
no Next Trainer instance is needed. nt.py itself is stdlib-only and loads
from its skill path via importlib.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

NT_PATH = Path(__file__).resolve().parents[1] / ".opencode/skills/next-trainer/scripts/nt.py"

spec = importlib.util.spec_from_file_location("nt_cli", NT_PATH)
nt = importlib.util.module_from_spec(spec)
sys.modules.setdefault("nt_cli", nt)
spec.loader.exec_module(nt)


def make_handler(routes: dict, posts: list):
    """routes: {(method, path): (status, payload_dict | bytes, content_type)}"""

    class Handler(BaseHTTPRequestHandler):
        def _handle(self, method):
            path = self.path.split("?")[0]
            key = (method, path)
            if key not in routes:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"detail": "not found"}).encode())
                return
            status, payload, *rest = routes[key]
            if isinstance(payload, bytes):
                ctype = rest[0] if rest else "application/octet-stream"
                body = payload
            else:
                ctype = "application/json"
                body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            posts.append(json.loads(self.rfile.read(length) or b"null"))
            self._handle("POST")

        def log_message(self, *args):
            pass

    return Handler


class NtCliTests(unittest.TestCase):
    def setUp(self):
        self.posts = []
        self.routes = {}
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.routes, self.posts))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = nt.main(["--base-url", self.base_url, *argv])
        return code, out.getvalue(), err.getvalue()

    def test_version_roundtrip(self):
        self.routes[("GET", "/api/version")] = (200, {"status": "success", "data": {"version": "3.0.0"}})
        code, out, _ = self.run_cli("version")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["version"], "3.0.0")

    def test_connection_error_is_clean(self):
        self.server.shutdown()
        self.server.server_close()
        code, _out, err = self.run_cli("version")
        self.assertEqual(code, 1)
        self.assertIn("无法连接", json.loads(err)["error"])

    def test_submit_gate_blocks_when_busy(self):
        self.routes[("GET", "/api/tasks")] = (200, {
            "status": "success",
            "data": {"tasks": [{"id": "t1", "status": "RUNNING", "lane": "compute"}]},
        })
        code, _out, err = self.run_cli("submit", '{"model_train_type": "sd-lora"}')
        self.assertEqual(code, 1)
        self.assertIn("已有 1 个任务", json.loads(err)["error"])
        self.assertEqual(self.posts, [])

    def test_submit_with_confirm_queue_posts(self):
        self.routes[("GET", "/api/tasks")] = (200, {
            "status": "success",
            "data": {"tasks": [{"id": "t1", "status": "RUNNING", "lane": "compute"}]},
        })
        self.routes[("POST", "/api/run")] = (200, {"status": "success", "data": {"task_id": "t2", "queued": True}})
        code, out, _ = self.run_cli("submit", '{"model_train_type": "sd-lora"}', "--confirm-queue")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["task_id"], "t2")
        self.assertEqual(self.posts[0]["model_train_type"], "sd-lora")

    def test_overview_composes_status_metrics_log_previews(self):
        self.routes[("GET", "/api/tasks")] = (200, {
            "status": "success",
            "data": {"tasks": [{"id": "t1", "status": "RUNNING", "metadata": {"train_type": "anima-lora"}}]},
        })
        self.routes[("GET", "/api/tasks/t1/metrics")] = (200, {
            "status": "success",
            "data": {"tags": {"loss/current": [{"step": 1, "value": 0.2}, {"step": 2, "value": 0.1}]},
                     "progress": {"percent": 50}},
        })
        self.routes[("GET", "/api/train/log/tail/t1")] = (200, {
            "status": "success", "data": {"lines": ["a", "b"], "done": False},
        })
        self.routes[("GET", "/api/tasks/t1/previews")] = (200, {
            "status": "success", "data": {"images": [{"name": "x.png"}]},
        })
        code, out, _ = self.run_cli("overview", "t1")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["task"]["train_type"], "anima-lora")
        self.assertEqual(data["latest_metrics"]["loss/current"]["value"], 0.1)
        self.assertEqual(data["log_tail"], ["a", "b"])
        self.assertEqual(data["preview_count"], 1)

    def test_preview_downloads_latest_to_disk(self):
        jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 16
        self.routes[("GET", "/api/tasks/t1/previews")] = (200, {
            "status": "success",
            "data": {"images": [{"name": "e1.png"}, {"name": "e2.png"}]},
        })
        self.routes[("GET", "/api/tasks/t1/previews/e2.png")] = (200, jpeg, "image/jpeg")
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            out_path = str(Path(tmp) / "preview.jpg")
            code, out, _ = self.run_cli("preview", "t1", "--out", out_path)
            self.assertEqual(code, 0)
            data = json.loads(out)
            self.assertEqual(data["name"], "e2.png")
            self.assertEqual(Path(out_path).read_bytes(), jpeg)

    def test_validate_posts_page_type_and_config(self):
        self.routes[("POST", "/api/config/validate-import")] = (200, {
            "status": "success", "data": {"errors": [], "warnings": []},
        })
        code, _out, _ = self.run_cli("validate", "anima-lora", '{"model_train_type": "anima-lora"}')
        self.assertEqual(code, 0)
        self.assertEqual(self.posts[0]["page_train_type"], "anima-lora")
        self.assertEqual(self.posts[0]["config"]["model_train_type"], "anima-lora")

    def test_dataset_validate_passthrough(self):
        self.routes[("POST", "/api/dataset/validate")] = (200, {
            "status": "success", "data": {"ok": False, "errors": ["未知字段 'recursive'"], "warnings": []},
        })
        code, out, _ = self.run_cli("dataset-validate", "/srv/ds.toml")
        self.assertEqual(code, 0)
        self.assertIn("recursive", out)
        self.assertEqual(self.posts[0]["path"], "/srv/ds.toml")

    def test_backend_fail_envelope_becomes_error(self):
        self.routes[("GET", "/api/version")] = (200, {"status": "fail", "message": "boom"})
        code, _out, err = self.run_cli("version")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(err)["error"], "boom")


if __name__ == "__main__":
    unittest.main()

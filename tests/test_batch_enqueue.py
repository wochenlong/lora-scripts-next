from __future__ import annotations

import asyncio
import io
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

stub_interrogator = types.ModuleType("mikazuki.tagger.interrogator")
stub_interrogator.available_interrogators = {}
stub_jobs = types.ModuleType("mikazuki.tagger.jobs")
stub_jobs.run_interrogate_job = lambda *args, **kwargs: None
stub_jobs.run_prefetch_job = lambda *args, **kwargs: None
stub_progress = types.ModuleType("mikazuki.tagger.progress")
stub_progress.tagger_progress = types.SimpleNamespace(
    get=lambda: {},
    request_cancel=lambda: False,
    is_busy=lambda: False,
    reset_idle=lambda message=None: None,
)
sys.modules.setdefault("mikazuki.tagger.interrogator", stub_interrogator)
sys.modules.setdefault("mikazuki.tagger.jobs", stub_jobs)
sys.modules.setdefault("mikazuki.tagger.progress", stub_progress)

from starlette.datastructures import UploadFile

from mikazuki.app import api
from mikazuki.app.models import APIResponseFail, APIResponseSuccess


def make_upload(name: str, content: bytes) -> UploadFile:
    return UploadFile(file=io.BytesIO(content), filename=name)


def run_endpoint(files):
    return asyncio.run(api.batch_enqueue_training(files))


VALID_TOML = b'model_train_type = "sd-lora"\noutput_name = "batch-test"\n'


class BatchEnqueueTests(unittest.TestCase):
    def setUp(self):
        self.dispatched: list[tuple[str, dict]] = []
        self._patches = [
            mock.patch.object(api.registry, "resolve_train_type", side_effect=lambda t: ("pack", "") if t == "sd-lora" else None),
            mock.patch.object(api, "dispatch_run", side_effect=self._fake_dispatch),
        ]
        for patcher in self._patches:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self._patches):
            patcher.stop()

    def _fake_dispatch(self, model_train_type, config, ctx):
        self.dispatched.append((model_train_type, dict(config)))
        return APIResponseSuccess(data={"task_id": f"task-{len(self.dispatched)}", "queued": True})

    def test_valid_toml_is_enqueued_and_staging_removed(self):
        with mock.patch("mikazuki.app.api.os.getcwd", return_value=self._tmp()):
            response = run_endpoint([make_upload("run1.toml", VALID_TOML)])
        data = response.data
        self.assertEqual(data["ok_count"], 1)
        self.assertEqual(data["fail_count"], 0)
        item = data["results"][0]
        self.assertTrue(item["ok"])
        self.assertTrue(item["queued"])
        self.assertEqual(self.dispatched[0][0], "sd-lora")
        self.assertNotIn("model_train_type", self.dispatched[0][1])
        # Successful configs live in autosave/task archives; the staging copy
        # is removed so the batch-queue dir does not accumulate.
        self.assertFalse(list(Path(data["queue_dir"]).glob("*-run1.toml")))

    def test_failed_file_stays_in_queue_dir(self):
        with mock.patch("mikazuki.app.api.os.getcwd", return_value=self._tmp()):
            response = run_endpoint([make_upload("bad.toml", b'output_name = "x"\n')])
        self.assertEqual(response.data["fail_count"], 1)
        self.assertFalse(self.dispatched)
        self.assertTrue(list(Path(response.data["queue_dir"]).glob("*-bad.toml")))

    def _tmp(self) -> str:
        import tempfile

        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        return td.name

    def test_missing_train_type_fails_without_dispatch(self):
        with mock.patch("mikazuki.app.api.os.getcwd", return_value=self._tmp()):
            response = run_endpoint([make_upload("bad.toml", b'output_name = "x"\n')])
        self.assertEqual(response.data["fail_count"], 1)
        self.assertIn("model_train_type", response.data["results"][0]["error"])
        self.assertFalse(self.dispatched)

    def test_unparseable_file_fails(self):
        with mock.patch("mikazuki.app.api.os.getcwd", return_value=self._tmp()):
            response = run_endpoint([make_upload("broken.toml", b"not = [valid")])
        self.assertEqual(response.data["fail_count"], 1)
        self.assertIn("解析失败", response.data["results"][0]["error"])

    def test_dispatch_failure_does_not_block_other_files(self):
        calls = {"n": 0}

        def flaky_dispatch(model_train_type, config, ctx):
            calls["n"] += 1
            if calls["n"] == 1:
                return APIResponseFail(message="preflight exploded")
            return APIResponseSuccess(data={"task_id": "task-2", "queued": False})

        with mock.patch.object(api, "dispatch_run", side_effect=flaky_dispatch):
            with mock.patch("mikazuki.app.api.os.getcwd", return_value=self._tmp()):
                response = run_endpoint([
                    make_upload("fail.toml", VALID_TOML),
                    make_upload("ok.toml", VALID_TOML),
                ])
        self.assertEqual(response.data["ok_count"], 1)
        self.assertEqual(response.data["fail_count"], 1)
        self.assertEqual(response.data["results"][0]["error"], "preflight exploded")
        self.assertFalse(response.data["results"][1]["queued"])

    def test_output_name_conflict_is_renamed(self):
        from mikazuki.tasks import TaskStatus

        blocker = api.tm.create_task([sys.executable, "-c", "pass"], {}, task_id="blocker-357",
                                     metadata={"output_name": "batch-test"})
        blocker.status = TaskStatus.RUNNING
        try:
            with mock.patch("mikazuki.app.api.os.getcwd", return_value=self._tmp()):
                response = run_endpoint([make_upload("run1.toml", VALID_TOML)])
        finally:
            blocker.status = TaskStatus.FINISHED
            api.tm.delete_task("blocker-357")
        item = response.data["results"][0]
        self.assertTrue(item["ok"])
        renamed = item["output_name_renamed"]
        self.assertEqual(renamed["from"], "batch-test")
        self.assertNotEqual(renamed["to"], "batch-test")
        self.assertEqual(self.dispatched[0][1]["output_name"], renamed["to"])

    def test_json_config_is_accepted(self):
        with mock.patch("mikazuki.app.api.os.getcwd", return_value=self._tmp()):
            response = run_endpoint([make_upload("run.json", b'{"model_train_type": "sd-lora"}')])
        self.assertEqual(response.data["ok_count"], 1)


if __name__ == "__main__":
    unittest.main()


def make_request(body: bytes) -> "object":
    from starlette.requests import Request

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": "POST", "path": "/api/tasks/auto_retry", "headers": []}, receive)


class AutoRetryApiTests(unittest.TestCase):
    def setUp(self):
        self._patch = mock.patch.object(api.tm, "set_global_auto_retry", side_effect=lambda c: c)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def _post(self, body: bytes):
        return asyncio.run(api.set_task_auto_retry(make_request(body)))

    def test_valid_count(self):
        response = self._post(b'{"count": 2}')
        self.assertEqual(response.status, "success")
        self.assertEqual(response.data["auto_retry_max"], 2)

    def test_scalar_body_is_rejected_not_500(self):
        for body in (b"[1]", b'"2"', b"2", b"true"):
            self.assertEqual(self._post(body).status, "fail", body)

    def test_non_integer_counts_rejected(self):
        for body in (b'{"count": "2"}', b'{"count": 2.5}', b'{"count": true}', b'{"count": -1}', b'{"count": 10}'):
            self.assertEqual(self._post(body).status, "fail", body)

    def test_invalid_json_rejected(self):
        self.assertEqual(self._post(b"{broken").status, "fail")

    def test_persist_failure_reports_fail(self):
        with mock.patch.object(api.tm, "set_global_auto_retry", side_effect=RuntimeError("disk full")):
            response = self._post(b'{"count": 1}')
        self.assertEqual(response.status, "fail")
        self.assertIn("保存失败", response.message)


class BatchArchiveUniquenessTests(unittest.TestCase):
    def test_same_second_batches_get_distinct_timestamps(self):
        import tempfile

        dispatched = []

        def fake_dispatch(model_train_type, config, ctx):
            dispatched.append(ctx.timestamp)
            return APIResponseSuccess(data={"task_id": "t", "queued": True})

        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(api.registry, "resolve_train_type", side_effect=lambda t: ("pack", "") if t == "sd-lora" else None), \
                mock.patch.object(api, "dispatch_run", side_effect=fake_dispatch), \
                mock.patch("mikazuki.app.api.os.getcwd", return_value=td):
            run_endpoint([make_upload("run1.toml", VALID_TOML)])
            run_endpoint([make_upload("run1.toml", VALID_TOML)])
        # Both succeeded, so staging copies are gone; what must differ are the
        # per-request autosave timestamps handed to the engine.
        self.assertEqual(len(dispatched), 2)
        self.assertEqual(len(set(dispatched)), 2)

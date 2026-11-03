"""R2只读查询：标准库小合同和微型真实worker，不安装/导入训练环境。"""
from __future__ import annotations

from collections import Counter
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from mikazuki.launcher import control, runtime, worker
from mikazuki.launcher.recipes import capabilities, recipe
from mikazuki.launcher.runtime import (ControlError, QueryControl, QueryStopped, RuntimeLayout,
                                      atomic_json, query_control, query_scope, sha_file)


def request(action="capabilities", *, scope="full", **extra):
    return {"schema_version": 1, "action": action,
            "query_protocol": {"version": 1, "task_id": "query-contract-1", "remaining_ms": 60000,
                               "progress": True, "scope": scope}, **extra}


class Clock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value


class QueryFixture:
    """只为单测声明微型内容闭包，不代表正式安装或环境健康验收。"""
    def __init__(self, root):
        self.root = root
        root.mkdir()
        (root / ".launcher-workspace").write_text("next-trainer-desktop-v1", encoding="utf-8")
        self.request = {"schema_version": 1, "action": "inspect_readonly", "root": str(root),
                        "release_id": "query-fixture", "engine_id": "kohya"}
        self.layout = RuntimeLayout(root, "query-fixture", "kohya", "t000000000000001")
        self.areas = {
            "environment": {"python.exe": b"synthetic interpreter", "pyvenv.cfg": b"synthetic config",
                            "Lib/site-packages/fixture.py": b"synthetic package content"},
            "source": {"train.py": b"synthetic source"},
        }
        roots = {"environment": self.layout.environment_root, "source": self.layout.engine_source_root}
        for area, values in self.areas.items():
            for relative, content in values.items():
                path = roots[area] / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
        base = self.layout.base_python_root / "python.exe"
        base.parent.mkdir(parents=True)
        base.write_bytes(b"synthetic base")
        receipt = {"schema_version": 1, "engine_id": "kohya", "release_id": "query-fixture",
                   "instance_id": self.layout.instance_id, "recipe_sha256": recipe("kohya")["recipe_sha256"],
                   "lock_sha256": "1" * 64, "generation": 1,
                   "files": {area: {name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                                    for name, data in values.items()} for area, values in self.areas.items()},
                   "package_files": {"Lib/site-packages/fixture.py": "synthetic-package"},
                   "base_python_files": {"python.exe": {"bytes": base.stat().st_size, "sha256": sha_file(base)}}}
        self.receipt_path = self.layout.state_root / "instances" / self.layout.instance_id / "1.json"
        atomic_json(self.receipt_path, receipt)
        state = {key: receipt[key] for key in ("engine_id", "release_id", "instance_id", "recipe_sha256", "lock_sha256")}
        state.update(schema_version=1, profile_id="default", generation=1, validated_generation=1,
                     dirty=False, status="ready", pending=None,
                     receipt_relative=f"instances/{self.layout.instance_id}/1.json", receipt_sha256=sha_file(self.receipt_path))
        atomic_json(self.layout.state_file, state)
        atomic_json(root / "state/registry.json", {"synthetic_marker": True})
        profile = root / "profiles/default/config/user.toml"
        profile.parent.mkdir(parents=True)
        profile.write_bytes(b"synthetic-user-data\n")

    def query(self, *, scope="full"):
        return {**self.request, "query_protocol": request(scope=scope)["query_protocol"]}

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob("*") if p.is_file()}


class QueryRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nt-query-", dir=os.environ.get("NEXT_TRAINER_QUERY_TEST_ROOT"))
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_no_protocol_keeps_old_result_and_no_query_context(self):
        self.assertEqual(control.dispatch({"action": "capabilities"}), capabilities())
        self.assertIsNone(query_control())

    def test_protocol_validation_happens_before_target_read(self):
        mutations = [
            ("version", True), ("version", 2), ("task_id", "../bad"), ("task_id", "x" * 193),
            ("remaining_ms", True), ("remaining_ms", -1), ("remaining_ms", 1800001),
            ("remaining_ms", 1.5), ("progress", "yes"), ("scope", "unsupported"),
        ]
        for key, value in mutations:
            with self.subTest(key=key, value=value), patch.object(control, "_layout", side_effect=AssertionError("target read")):
                r = request("inspect_readonly")
                r["query_protocol"][key] = value
                with self.assertRaises(ControlError):
                    control.dispatch(r)
        for action in ("repair_apply", "recover", "probe_execute", "availability", []):
            with self.subTest(action=action), self.assertRaises(ControlError):
                control.dispatch(request(action))
        for protocol in (None, [], "invalid"):
            with self.subTest(protocol=protocol), self.assertRaises(ControlError):
                control.dispatch({"action": "capabilities", "query_protocol": protocol})

    def test_cancel_file_is_rejected_for_query_even_if_none(self):
        for value in (None, "", "F:/not-authorized"):
            with self.subTest(value=value), self.assertRaisesRegex(ControlError, "取消文件"):
                control.dispatch(request(cancel_file=value))

    def test_scopes_are_explicit_and_full_files_only_have_identical_integrity(self):
        fixture = QueryFixture(self.root / "workspace")
        before = fixture.snapshot()
        full = control.dispatch(fixture.query())
        files_only = control.dispatch(fixture.query(scope="files_only"))
        self.assertEqual(full, files_only)
        self.assertEqual(full["installation"], "ready")
        self.assertEqual(full["import"], "not_checked")
        self.assertEqual(before, fixture.snapshot())
        for action, scope in (("capabilities", "plan"), ("inspect_readonly", "plan"), ("plan_install", "full")):
            with self.subTest(action=action, scope=scope), self.assertRaises(ControlError):
                control.dispatch(request(action, scope=scope))

    def test_zero_remaining_stops_before_dispatch_and_context_resets(self):
        r = request()
        r["query_protocol"]["remaining_ms"] = 0
        with patch.object(control, "capabilities", side_effect=AssertionError("dispatch called")):
            with self.assertRaises(QueryStopped) as error:
                control.dispatch(r)
        self.assertEqual(error.exception.code, "query_timed_out")
        self.assertIsNone(query_control())
        self.assertEqual(control.dispatch({"action": "capabilities"}), capabilities())

    def test_single_deadline_does_not_refresh_on_progress_or_stage(self):
        clock, frames = Clock(), []
        query = QueryControl("unit-1", 1000, "full", clock=clock, emit=frames.append)
        original = query.deadline
        with query_scope(query):
            clock.value += 0.6
            runtime.query_stage("environment")
            runtime.query_checkpoint(read_bytes=12)
            self.assertEqual(query.deadline, original)
            clock.value += 0.5
            with self.assertRaises(QueryStopped) as error:
                runtime.query_checkpoint()
        self.assertEqual(error.exception.code, "query_timed_out")

    def test_real_hash_preserves_digest_and_counts_only_actual_reads(self):
        path = self.root / "payload.bin"
        data = b"a" * (runtime.QUERY_CHUNK_BYTES + 7)
        path.write_bytes(data)
        query = QueryControl("unit-1", 60000, "full")
        with query_scope(query):
            self.assertEqual(sha_file(path), hashlib.sha256(data).hexdigest())
        self.assertEqual((query.files, query.bytes), (1, len(data)))
        empty = self.root / "empty"
        empty.write_bytes(b"")
        with query_scope(query):
            self.assertEqual(sha_file(empty), hashlib.sha256(b"").hexdigest())
        self.assertEqual((query.files, query.bytes), (2, len(data)))

    def test_hash_cancellation_stops_before_next_chunk_and_keeps_actual_bytes(self):
        stream = io.BytesIO(b"x" * (3 * runtime.QUERY_CHUNK_BYTES))
        original_read = stream.read
        reads = []
        def counted_read(size):
            value = original_read(size)
            reads.append(len(value))
            return value
        stream.read = counted_read
        query = QueryControl("unit-1", 60000, "full", cancelled=lambda: bool(reads))
        with query_scope(query), patch.object(Path, "open", return_value=stream):
            with self.assertRaises(QueryStopped) as error:
                sha_file(self.root / "virtual-file")
        self.assertEqual(error.exception.code, "query_cancelled")
        self.assertEqual(reads, [runtime.QUERY_CHUNK_BYTES])
        self.assertEqual(query.bytes, runtime.QUERY_CHUNK_BYTES)
        self.assertEqual(query.files, 0)
        self.assertTrue(stream.closed)

    def test_hash_timeout_stops_after_current_chunk_and_before_next_read(self):
        clock, stream = Clock(), io.BytesIO(b"x" * (3 * runtime.QUERY_CHUNK_BYTES))
        original_read, reads = stream.read, []
        def counted_read(size):
            value = original_read(size)
            reads.append(len(value))
            clock.value += 2
            return value
        stream.read = counted_read
        query = QueryControl("unit-1", 1000, "full", clock=clock)
        with query_scope(query), patch.object(Path, "open", return_value=stream):
            with self.assertRaises(QueryStopped) as error:
                sha_file(self.root / "virtual-file")
        self.assertEqual(error.exception.code, "query_timed_out")
        self.assertEqual(reads, [runtime.QUERY_CHUNK_BYTES])
        self.assertEqual(query.bytes, runtime.QUERY_CHUNK_BYTES)

    def test_query_json_reads_are_bounded_utf8_and_cancellable(self):
        path = self.root / "state.json"
        payload = {"text": "中文", "number": 3}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        query = QueryControl("unit-1", 60000, "full")
        with query_scope(query):
            self.assertEqual(runtime.read_json(path), payload)
            with self.assertRaises(ControlError) as error:
                runtime.read_json(path, limit=1)
        self.assertEqual(error.exception.code, "state_too_large")
        self.assertEqual(query.bytes, path.stat().st_size)
        query = QueryControl("unit-1", 60000, "full", cancelled=lambda: True)
        with self.assertRaises(QueryStopped), query_scope(query):
            runtime.read_json(path)

    def test_directory_scan_checks_each_entry_and_preserves_bytecode_filter(self):
        root = self.root / "tree"
        (root / "nested").mkdir(parents=True)
        (root / "__pycache__").mkdir()
        for relative, data in (("a.py", b"a"), ("nested/b.py", b"b"),
                               ("cached.pyc", b"skip"), ("__pycache__/derived.bin", b"skip")):
            (root / relative).write_bytes(data)
        legacy = control._tree(root, self.root)
        query = QueryControl("unit-1", 60000, "full")
        with query_scope(query):
            self.assertEqual(control._tree(root, self.root), legacy)
        self.assertEqual(set(legacy), {"a.py", "nested/b.py"})
        self.assertEqual((query.files, query.bytes), (2, 2))
        query = QueryControl("unit-1", 60000, "full", cancelled=lambda: query.files >= 1)
        with query_scope(query), self.assertRaises(QueryStopped):
            control._tree(root, self.root)
        self.assertEqual(query.files, 1)

    def test_query_directory_scan_still_rejects_reparse(self):
        root = self.root / "tree"
        (root / "linked").mkdir(parents=True)
        actual = runtime.is_reparse
        with patch.object(runtime, "is_reparse", side_effect=lambda p: p == root / "linked" or actual(p)):
            with query_scope(QueryControl("unit-1", 60000, "full")), self.assertRaises(ControlError) as error:
                control._tree(root, self.root)
        self.assertEqual(error.exception.code, "unexpected_reparse")

    def test_progress_is_limited_per_stage_and_never_invents_totals(self):
        clock, frames = Clock(), []
        query = QueryControl("unit-1", 60000, "full", clock=clock, emit=frames.append)
        with query_scope(query):
            for _ in range(100):
                runtime.query_checkpoint(read_bytes=1)
            self.assertEqual(len(frames), 1)
            clock.value += 0.25
            runtime.query_checkpoint(file_complete=True)
            self.assertEqual(len(frames), 2)
            self.assertEqual((frames[-1]["files"], frames[-1]["bytes"]), (1, 100))
            runtime.query_stage("source")
            self.assertEqual((frames[-1]["files"], frames[-1]["bytes"]), (0, 0))
        self.assertEqual([frame["seq"] for frame in frames], list(range(1, len(frames) + 1)))
        for frame in frames:
            self.assertIsNone(frame["total_files"])
            self.assertIsNone(frame["total_bytes"])
            self.assertLess(len(frame["message"].encode()), 4096)
            self.assertLess(len(json.dumps(frame).encode()), worker.PROGRESS_LIMIT)

    def test_progress_frame_limit_does_not_disable_deadline_checks(self):
        clock, frames = Clock(), []
        query = QueryControl("unit-1", 1000, "full", clock=clock, emit=frames.append)
        query.seq = 8192
        with query_scope(query):
            runtime.query_checkpoint(read_bytes=1)
            self.assertEqual(frames, [])
            clock.value += 2
            with self.assertRaises(QueryStopped):
                runtime.query_checkpoint()

    def test_disabled_progress_still_checks_deadline(self):
        r = request()
        r["query_protocol"]["progress"] = False
        frames = []
        query = QueryControl.from_request(r, emit=frames.append)
        self.assertEqual(control.dispatch(r, query=query), capabilities())
        self.assertEqual(frames, [])

    def test_progress_pipe_failure_stops_inspect_and_does_not_become_unknown(self):
        fixture = QueryFixture(self.root / "workspace")
        calls = []
        def broken(frame):
            calls.append(frame["stage"])
            if frame["stage"] == "environment":
                raise BrokenPipeError("closed")
        query = QueryControl.from_request(fixture.query(), emit=broken)
        with self.assertRaises(QueryStopped) as error:
            control.dispatch(fixture.query(), query=query)
        self.assertEqual(error.exception.code, "query_output_closed")
        self.assertIn("environment", calls)

    def test_cancel_and_timeout_are_not_swallowed_by_inspect(self):
        fixture = QueryFixture(self.root / "workspace")
        for code in ("query_cancelled", "query_timed_out"):
            with self.subTest(code=code), patch.object(control, "_tree", side_effect=QueryStopped(code, "stop")):
                with self.assertRaises(QueryStopped) as error:
                    control.dispatch(fixture.query())
                self.assertEqual(error.exception.code, code)

    def test_plan_asset_capture_does_not_swallow_query_stop(self):
        root = self.root / "missing"
        r = request("plan_install", scope="plan", root=str(root), release_id="unit", engine_id="kohya")
        lock = {"uv": {"filename": "synthetic.exe"}, "wheels": [], "source": {}, "python": {}}
        with patch.object(control, "_lock", return_value=lock), patch.object(
                control, "_asset", side_effect=QueryStopped("query_timed_out", "stop")):
            with self.assertRaises(QueryStopped) as error:
                control.dispatch(r)
        self.assertEqual(error.exception.code, "query_timed_out")
        self.assertFalse(root.exists())

    def test_success_and_mid_scan_cancel_leave_entire_synthetic_tree_unchanged(self):
        fixture = QueryFixture(self.root / "workspace")
        before = fixture.snapshot()
        self.assertEqual(control.dispatch(fixture.query())["installation"], "ready")
        query = QueryControl.from_request(fixture.query())
        query.cancelled = lambda: query.stage == "environment" and query.files >= 1
        with self.assertRaises(QueryStopped):
            control.dispatch(fixture.query(), query=query)
        self.assertEqual(before, fixture.snapshot())
        self.assertFalse((fixture.root / "tools").exists())
        self.assertIsNone(query_control())

    def test_complete_scan_hashes_actual_environment_source_and_base_once(self):
        fixture = QueryFixture(self.root / "workspace")
        with patch.object(control, "sha_file", wraps=sha_file) as hashes:
            value = control.dispatch(fixture.query())
        self.assertEqual(value["installation"], "ready")
        expected = [fixture.receipt_path, fixture.layout.base_python_root / "python.exe"]
        for area, files in fixture.areas.items():
            root = fixture.layout.environment_root if area == "environment" else fixture.layout.engine_source_root
            expected.extend(root / name for name in files)
        self.assertEqual(Counter(Path(call.args[0]) for call in hashes.call_args_list), Counter(expected))

    def test_legacy_cancel_context_is_restored_for_success_and_failure(self):
        sentinel = self.root / "outer-cancel"
        token = control._CANCEL_PATH.set(sentinel)
        try:
            self.assertEqual(control.dispatch({"action": "capabilities"}), capabilities())
            self.assertEqual(control._CANCEL_PATH.get(), sentinel)
            with self.assertRaises(ControlError):
                control.dispatch({"action": "unknown"})
            self.assertEqual(control._CANCEL_PATH.get(), sentinel)
            with patch.object(control, "repair_apply", side_effect=lambda r: str(control._CANCEL_PATH.get())):
                r = {"action": "repair_apply", "root": str(self.root), "release_id": "unit", "engine_id": "kohya",
                     "cancel_file": str(self.root / "state" / "unit.cancel")}
                self.assertEqual(control.dispatch(r), str(self.root / "state" / "unit.cancel"))
            self.assertEqual(control._CANCEL_PATH.get(), sentinel)
        finally:
            control._CANCEL_PATH.reset(token)


class WorkerProtocolTests(unittest.TestCase):
    def run_inline(self, r):
        output = io.StringIO()
        status = worker.run_request(r, output)
        frames = [json.loads(line) for line in output.getvalue().splitlines()]
        return status, frames

    def test_legacy_success_failure_and_mutation_are_single_original_envelopes(self):
        for r in ({"action": "capabilities"}, {"action": "unknown"}):
            status, frames = self.run_inline(r)
            self.assertEqual(len(frames), 1)
            self.assertEqual(set(frames[0]), {"schema_version", "ok", "result" if status == 0 else "error"})
        with patch.object(control, "repair_apply", return_value={"status": "synthetic"}):
            status, frames = self.run_inline({"action": "repair_apply"})
        self.assertEqual((status, frames), (0, [{"schema_version": 1, "ok": True, "result": {"status": "synthetic"}}]))

    def test_query_stream_has_progress_and_exactly_one_final_with_scope(self):
        status, frames = self.run_inline(request())
        self.assertEqual(status, 0)
        self.assertEqual([f["type"] for f in frames], ["progress", "result"])
        self.assertEqual(frames[-1]["result"], capabilities())
        self.assertEqual(frames[-1]["scope"], "full")
        self.assertTrue(all(f["task_id"] == "query-contract-1" for f in frames))

    def test_query_zero_deadline_has_one_error_final_and_no_work(self):
        r = request()
        r["query_protocol"]["remaining_ms"] = 0
        status, frames = self.run_inline(r)
        self.assertEqual(status, 1)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0]["type"], "result")
        self.assertEqual(frames[0]["error"]["code"], "query_timed_out")

    def test_large_final_fails_without_publishing_partial_frame(self):
        with patch.object(control, "capabilities", return_value={"large": "x" * worker.RESULT_LIMIT}):
            status, frames = self.run_inline(request())
        self.assertEqual(status, 1)
        self.assertEqual([f["type"] for f in frames], ["progress", "result"])
        self.assertEqual(frames[-1]["error"]["code"], "query_output_too_large")

    def test_large_error_is_utf8_bounded_and_one_final(self):
        with patch.object(control, "capabilities", side_effect=ControlError("test_error", "文" * 5000)):
            status, frames = self.run_inline(request())
        self.assertEqual(status, 1)
        self.assertEqual(frames[-1]["type"], "result")
        self.assertLessEqual(len(frames[-1]["error"]["message"].encode()), 4096)

    def test_closed_output_does_not_keep_writing_or_call_dispatch(self):
        class Closed:
            calls = 0
            def write(self, value):
                self.calls += 1
                raise BrokenPipeError("closed")
            def flush(self):
                pass
        output = Closed()
        with patch.object(control, "capabilities", side_effect=AssertionError("must stop before work")):
            self.assertEqual(worker.run_request(request(), output), 1)
        self.assertEqual(output.calls, 1)

    def test_frame_size_guard_is_exact_in_utf8_bytes(self):
        output = io.StringIO()
        with self.assertRaises(ControlError):
            worker._write_frame(output, {"large": "文" * worker.PROGRESS_LIMIT}, worker.PROGRESS_LIMIT)
        self.assertEqual(output.getvalue(), "")

    def test_real_worker_legacy_and_query_and_missing_do_not_create_root(self):
        with tempfile.TemporaryDirectory(prefix="nt-query-worker-", dir=os.environ.get("NEXT_TRAINER_QUERY_TEST_ROOT")) as temp:
            root = Path(temp) / "missing"
            cases = [{"schema_version": 1, "action": "capabilities"}, request(),
                     request("inspect_readonly", scope="files_only", root=str(root), release_id="unit", engine_id="kohya")]
            for r in cases:
                with self.subTest(action=r["action"], query="query_protocol" in r):
                    done = subprocess.run([sys.executable, "-I", "-B", "-S", str(Path(worker.__file__))],
                                          input=json.dumps(r) + "\n", capture_output=True, text=True, encoding="utf-8", timeout=15)
                    self.assertEqual(done.returncode, 0, done.stderr)
                    frames = [json.loads(line) for line in done.stdout.splitlines()]
                    self.assertTrue(frames[-1]["ok"])
                    if "query_protocol" in r:
                        self.assertEqual(frames[-1]["type"], "result")
                        self.assertEqual(frames[-1]["scope"], r["query_protocol"]["scope"])
                    else:
                        self.assertEqual(len(frames), 1)
                        self.assertNotIn("type", frames[0])
            self.assertFalse(root.exists())

    def test_real_worker_bad_or_oversized_input_returns_single_error(self):
        for payload in ("{broken\n", "x" * (worker.REQUEST_LIMIT + 1) + "\n"):
            with self.subTest(size=len(payload)):
                done = subprocess.run([sys.executable, "-I", "-B", "-S", str(Path(worker.__file__))],
                                      input=payload, capture_output=True, text=True, encoding="utf-8", timeout=15)
                self.assertEqual(done.returncode, 1)
                frames = [json.loads(line) for line in done.stdout.splitlines()]
                self.assertEqual(len(frames), 1)
                self.assertFalse(frames[0]["ok"])


if __name__ == "__main__":
    unittest.main()

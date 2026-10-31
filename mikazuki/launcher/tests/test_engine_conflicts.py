"""真实跨进程锁与微型训练生命周期冒烟；不下载依赖，不调用 GPU。"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import psutil

from mikazuki.launcher import control
from mikazuki.launcher.bindings import bind_training_task, managed_preflight_lease
from mikazuki.launcher.runtime import ControlError, RuntimeLayout, engine_activity, engine_lease
from mikazuki.launcher.tests.test_control_smoke import EngineFixture
from mikazuki.tasks import Task, TaskManager, TaskStatus


@contextmanager
def process_lease(layout, *, workspace=False, shared=False, mode="mutation"):
    code = "\n".join([
        "import sys",
        "from pathlib import Path",
        "from mikazuki.launcher.runtime import RuntimeLayout,workspace_lease,engine_lease",
        f"layout=RuntimeLayout(Path({str(layout.root)!r}), {layout.release_id!r}, {layout.engine_id!r})",
        f"lease=workspace_lease(layout,shared={shared!r})" if workspace else f"lease=engine_lease(layout,mode={mode!r})",
        "with lease:",
        " print('ready',flush=True)",
        " sys.stdin.readline()",
    ])
    process = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8")
    try:
        if process.stdout.readline().strip() != "ready":
            raise AssertionError(process.communicate(timeout=10)[1])
        yield process
    finally:
        if process.poll() is None:
            process.communicate("release\n", timeout=10)
        else:
            process.communicate(timeout=10)


class EngineConflictSmoke(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="nt-engine-conflicts-")
        self.fixture = EngineFixture(Path(self.temporary.name) / "workspace")

    def tearDown(self):
        self.temporary.cleanup()

    def context(self):
        f = self.fixture
        return patch.dict(os.environ, {"NEXT_TRAINER_LAUNCHER_CONTEXT": json.dumps({
            "schema_version": 1, "root": str(f.root), "release_id": f.layout.release_id,
            "engine_catalog": {"kohya": {"lock_path": f.request["lock_path"], "sha256": f.request["lock_sha256"]}},
        })})

    def task(self, command=None):
        metadata = {"backend": "standard"}
        bind_training_task(metadata)
        return Task("fixture-training", command or [sys.executable, "-c", "import time; time.sleep(0.4)"],
                    dict(os.environ), metadata=metadata)

    def unchanged_apply(self):
        planned = control.plan(self.fixture.request)
        return control.repair_apply({**self.fixture.request, "plan": planned, "plan_sha256": planned["plan_sha256"]})

    def test_running_service_and_other_engine_training_allow_install(self):
        other = RuntimeLayout(self.fixture.root, "another-release", "anima-fast")
        with process_lease(self.fixture.layout, workspace=True, shared=True), process_lease(other, mode="training"):
            before = sorted(str(p.relative_to(self.fixture.root)) for p in self.fixture.root.rglob("*"))
            self.assertEqual(control.inspect_readonly(self.fixture.request)["installation"], "missing")
            self.assertEqual(control.plan(self.fixture.request, installing=True)["kind"], "install")
            self.assertEqual(before, sorted(str(p.relative_to(self.fixture.root)) for p in self.fixture.root.rglob("*")))
            self.assertEqual(self.fixture.install()["status"], "succeeded")

    def test_main_program_mutation_blocks_engine_write_but_not_readonly(self):
        self.fixture.install()
        with process_lease(self.fixture.layout, workspace=True):
            self.assertEqual(control.inspect_readonly(self.fixture.request)["installation"], "ready")
            self.assertEqual(control.plan(self.fixture.request)["kind"], "repair")
            with self.assertRaises(ControlError) as caught:
                self.unchanged_apply()
            self.assertEqual(caught.exception.code, "workspace_busy")

    def test_same_engine_use_across_releases_blocks_only_its_write(self):
        self.fixture.install()
        other_release = RuntimeLayout(self.fixture.root, "another-release", "kohya")
        with process_lease(other_release, mode="training"):
            before = {str(p): p.read_bytes() for p in self.fixture.root.rglob("*") if p.is_file()}
            report = control.inspect_readonly(self.fixture.request)
            self.assertEqual(report["activity"]["kind"], "training")
            control.plan(self.fixture.request)
            self.assertEqual(before, {str(p): p.read_bytes() for p in self.fixture.root.rglob("*") if p.is_file()})
            with self.assertRaises(ControlError) as caught:
                self.unchanged_apply()
            self.assertEqual(caught.exception.code, "engine_busy")
            with engine_lease(RuntimeLayout(self.fixture.root, "fixture-v1", "ai-toolkit")):
                pass
        self.assertEqual(self.unchanged_apply()["status"], "no_changes")

    def test_running_repair_blocks_training_start(self):
        self.fixture.install()
        with self.context():
            task = self.task()
            with process_lease(self.fixture.layout):
                self.assertEqual(control.inspect_readonly(self.fixture.request)["activity"]["kind"], "operation")
                with self.assertRaises(ControlError) as caught:
                    task.execute()
                self.assertEqual(caught.exception.code, "engine_busy")
                self.assertIsNone(getattr(task, "process", None))
                self.assertEqual(task.status, TaskStatus.FAILED)

    def test_real_training_process_holds_target_until_exit(self):
        self.fixture.install()
        with self.context():
            task = self.task()
            try:
                with managed_preflight_lease("kohya"):
                    # handler 的预检共享锁与刚提交的 worker 使用锁可以重叠。
                    task.execute()
                self.assertEqual(engine_activity(self.fixture.layout)["kind"], "training")
                with self.assertRaises(ControlError) as caught:
                    self.unchanged_apply()
                self.assertEqual(caught.exception.code, "engine_busy")
                task.wait()
                self.assertFalse(engine_activity(self.fixture.layout)["busy"])
                self.assertEqual(self.unchanged_apply()["status"], "no_changes")
            finally:
                if getattr(task, "process", None) is not None and task.process.poll() is None:
                    task.terminate()
                    task.wait()

    def test_spawn_failure_and_cancel_release_target(self):
        self.fixture.install()
        with self.context():
            failed = self.task([str(self.fixture.root / "missing-python.exe")])
            failed.execute()
            failed.wait()
            self.assertEqual(failed.returncode, 125)
            self.assertFalse(engine_activity(self.fixture.layout)["busy"])
            failed = self.task()
            with patch("mikazuki.tasks.subprocess.Popen", side_effect=FileNotFoundError("missing supervisor interpreter")), self.assertRaises(OSError):
                failed.execute()
            self.assertFalse(engine_activity(self.fixture.layout)["busy"])
            task = self.task([sys.executable, "-c", "import time; time.sleep(20)"])
            task.execute()
            task.terminate()
            task.wait()
            self.assertEqual(task.status, TaskStatus.TERMINATED)
            self.assertFalse(engine_activity(self.fixture.layout)["busy"])

    def test_queued_old_binding_is_rejected_before_spawn(self):
        self.fixture.install()
        with self.context():
            manager = TaskManager()
            task = manager.create_task([sys.executable, "-c", "pass"], dict(os.environ), metadata={"backend": "standard"})
            self.assertFalse(engine_activity(self.fixture.layout)["busy"])
            planned = control.plan({**self.fixture.request, "rebuild": True}, installing=True)
            with patch.object(control, "_run", self.fixture.run):
                control.repair_apply({**self.fixture.request, "plan": planned, "plan_sha256": planned["plan_sha256"]})
            with self.assertRaises(ControlError) as caught:
                task.execute()
            self.assertEqual(caught.exception.code, "training_binding_changed")
            self.assertIsNone(getattr(task, "process", None))
            self.assertFalse(engine_activity(self.fixture.layout)["busy"])

    def test_process_exit_releases_even_without_caller_wait(self):
        self.fixture.install()
        with self.context():
            task = self.task([sys.executable, "-c", "pass"])
            task.execute()
            task.process.wait(timeout=10)
            deadline = time.monotonic() + 5
            while engine_activity(self.fixture.layout)["busy"] and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertFalse(engine_activity(self.fixture.layout)["busy"])
            task.wait()

    def test_training_start_and_mutation_race_have_single_winner(self):
        code = "\n".join([
            "import sys",
            "from pathlib import Path",
            "from mikazuki.launcher.runtime import RuntimeLayout,engine_lease,ControlError",
            f"layout=RuntimeLayout(Path({str(self.fixture.root)!r}),'fixture-v1','kohya')",
            "print('ready',flush=True)",
            "sys.stdin.readline()",
            "try:",
            " with engine_lease(layout,mode=sys.argv[1]):",
            "  print('acquired',flush=True)",
            "  sys.stdin.readline()",
            "except ControlError as error:",
            " print(error.code,flush=True)",
        ])
        processes = [subprocess.Popen([sys.executable, "-c", code, mode], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      text=True, encoding="utf-8") for mode in ("training", "mutation")]
        try:
            for process in processes:
                self.assertEqual(process.stdout.readline().strip(), "ready")
            for process in processes:
                process.stdin.write("go\n")
                process.stdin.flush()
            outcomes = [process.stdout.readline().strip() for process in processes]
            self.assertCountEqual(outcomes, ["acquired", "engine_busy"])
        finally:
            for process in processes:
                if process.poll() is None:
                    process.communicate("release\n", timeout=10)
                else:
                    process.communicate(timeout=10)

    def test_wait_finishes_after_inflight_unlock_completes(self):
        lease = engine_lease(self.fixture.layout, mode="training")
        lease.__enter__()
        unlocking, permit_unlock, waited = threading.Event(), threading.Event(), threading.Event()
        class DelayedUnlock:
            def __exit__(self, *args):
                unlocking.set()
                if not permit_unlock.wait(timeout=10):
                    raise AssertionError("unlock was not resumed")
                lease.__exit__(*args)
        task = Task("unlock-race", [sys.executable, "-c", "pass"])
        task.execute()
        task.process.wait(timeout=10)
        task._managed_training_lease = DelayedUnlock()
        unlocking_thread = threading.Thread(target=task._release_training_lease)
        waiting_thread = threading.Thread(target=lambda: (task.wait(), waited.set()))
        try:
            unlocking_thread.start()
            self.assertTrue(unlocking.wait(timeout=5))
            waiting_thread.start()
            self.assertFalse(waited.wait(timeout=0.05))
            self.assertTrue(engine_activity(self.fixture.layout)["busy"])
        finally:
            permit_unlock.set()
            unlocking_thread.join(timeout=10)
            if waiting_thread.ident is not None:
                waiting_thread.join(timeout=10)
        self.assertTrue(waited.is_set())
        self.assertFalse(engine_activity(self.fixture.layout)["busy"])

    def wait_path(self, path, timeout=10):
        deadline = time.monotonic() + timeout
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(path.exists(), str(path))

    def orphan_command(self, seconds, *, returncode=7):
        pid_file = self.fixture.root / "worker.pid"
        parent_exit = self.fixture.root / "parent-exited"
        complete = self.fixture.root / "worker-complete"
        child = (f"import os,time; from pathlib import Path; Path({str(pid_file)!r}).write_text(str(os.getpid())); "
                 f"time.sleep({seconds}); Path({str(complete)!r}).write_text('complete')")
        parent = (f"import subprocess,sys; from pathlib import Path; "
                  f"subprocess.Popen([sys.executable,'-c',{child!r}],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
                  f"Path({str(parent_exit)!r}).write_text('exited'); sys.exit({returncode})")
        return [sys.executable, "-c", parent], pid_file, parent_exit, complete

    def test_supervisor_waits_for_redirected_orphan_worker(self):
        self.fixture.install()
        command, pid_file, parent_exit, complete = self.orphan_command(0.8)
        with self.context():
            task = self.task(command)
            try:
                task.execute()
                self.wait_path(pid_file)
                self.wait_path(parent_exit)
                self.assertIsNone(task.process.poll())
                self.assertTrue(engine_activity(self.fixture.layout)["busy"])
                task.wait()
                self.assertEqual(task.returncode, 7)
                self.assertTrue(complete.exists())
                self.assertFalse(engine_activity(self.fixture.layout)["busy"])
            finally:
                if getattr(task, "process", None) is not None and task.process.poll() is None:
                    task.terminate()
                    task.wait()

    @unittest.skipUnless(os.name == "nt", "Windows Job 关闭时自动清空孤儿子树")
    def test_cancel_and_supervisor_crash_clear_orphan_tree(self):
        self.fixture.install()
        for stop in ("cancel", "supervisor-crash"):
            with self.subTest(stop=stop), self.context():
                for path in (self.fixture.root / "worker.pid", self.fixture.root / "parent-exited"):
                    path.unlink(missing_ok=True)
                command, pid_file, parent_exit, complete = self.orphan_command(20)
                task = self.task(command)
                try:
                    task.execute()
                    self.wait_path(pid_file)
                    self.wait_path(parent_exit)
                    worker = psutil.Process(int(pid_file.read_text()))
                    self.assertTrue(worker.is_running())
                    if stop == "cancel":
                        task.terminate()
                    else:
                        task.process.kill()
                    task.wait()
                    worker.wait(timeout=10)
                    self.assertFalse(worker.is_running())
                    self.assertFalse(complete.exists())
                    self.assertFalse(engine_activity(self.fixture.layout)["busy"])
                finally:
                    if getattr(task, "process", None) is not None and task.process.poll() is None:
                        task.terminate()
                        task.wait()

    @unittest.skipUnless(os.name == "nt", "Windows 桌面服务 Job 与训练 Job 可嵌套")
    def test_nested_supervisor_jobs_keep_exit_code(self):
        supervisor = Path(control.__file__).with_name("training_supervisor.py")
        command = [sys.executable, "-I", "-B", "-S", str(supervisor), "--"]
        result = subprocess.run([*command, *command, sys.executable, "-c", "raise SystemExit(9)"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 9, result.stderr)


if __name__ == "__main__":
    unittest.main()

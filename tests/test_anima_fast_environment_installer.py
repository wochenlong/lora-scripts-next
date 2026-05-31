from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock
import subprocess

from mikazuki.anima_fast_backend.environment import (
    AuditResult,
    audit_environment,
    build_environment_install_plan,
    install_environment,
    _run_streaming,
    start_install_task,
)
from mikazuki.anima_fast_backend.extension_state import (
    STATE_BROKEN,
    STATE_INSTALLED_UNVERIFIED,
    STATE_READY,
    ExtensionLayout,
    read_extension_status,
)
from mikazuki.tasks import tm


class AnimaFastEnvironmentInstallerTests(unittest.TestCase):
    def _make_source(self, root: Path) -> Path:
        source = root / "anima_source"
        source.mkdir()
        (source / "train.py").write_text("print('train')", encoding="utf-8")
        (source / "pyproject.toml").write_text("[project]\nname='anima-test'\n", encoding="utf-8")
        (source / "configs").mkdir()
        (source / "configs" / "base.toml").write_text("", encoding="utf-8")
        return source

    def _make_constraints(self, project: Path) -> None:
        env_dir = project / "config" / "anima_fast_environment"
        env_dir.mkdir(parents=True)
        (env_dir / "anima-constraints-cu130.txt").write_text("torch==2.11.0+cu130\n", encoding="utf-8")
        (env_dir / "anima-overrides-cu130.txt").write_text("numpy>=2\n", encoding="utf-8")

    def test_ready_requires_audit_ok_facts(self):
        with tempfile.TemporaryDirectory() as td:
            layout = ExtensionLayout(Path(td) / "extensions" / "anima_lora")
            layout.source.mkdir(parents=True)
            layout.train_py.write_text("", encoding="utf-8")
            layout.venv_python.parent.mkdir(parents=True)
            layout.venv_python.write_text("", encoding="utf-8")
            from mikazuki.anima_fast_backend.extension_state import write_install_state

            write_install_state(layout, STATE_READY, {"audit": {"ok": False}})

            status = read_extension_status(layout)

        self.assertEqual(status.state, STATE_INSTALLED_UNVERIFIED)
        self.assertIn("audit", status.reason)

    def test_install_environment_writes_ready_only_after_audit_passes(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            source = self._make_source(project)
            self._make_constraints(project)
            layout = ExtensionLayout(project / "extensions" / "anima_lora")
            plan = build_environment_install_plan(project, layout, source, dry_run=False, source_commit="abc123")

            discovered_python = plan.python_install_dir / "cpython-3.13.99-windows-x86_64-none" / "python.exe"

            def fake_run(command, cwd, log, env=None, retries=0):
                if len(command) >= 3 and command[0] == str(discovered_python) and command[1:3] == ["-m", "venv"]:
                    plan.venv_python.parent.mkdir(parents=True)
                    plan.venv_python.write_text("", encoding="utf-8")
                if len(command) >= 3 and command[1:3] == ["python", "install"]:
                    discovered_python.parent.mkdir(parents=True)
                    discovered_python.write_text("", encoding="utf-8")
                log("[fake] command completed")

            def fake_copy(_plan):
                layout.source.mkdir(parents=True)
                layout.train_py.write_text("print('train')\n", encoding="utf-8")

            with mock.patch("mikazuki.anima_fast_backend.environment._uv_command", return_value="uv"), \
                mock.patch("mikazuki.anima_fast_backend.environment.copy_source_snapshot", side_effect=fake_copy), \
                mock.patch("mikazuki.anima_fast_backend.environment._run_streaming", side_effect=fake_run), \
                mock.patch(
                    "mikazuki.anima_fast_backend.environment.audit_environment",
                    return_value=AuditResult(ok=True, facts={"anima": {"torch": "2.11.0+cu130"}}),
                ):
                result = install_environment(plan, lambda _line: None)

            status = read_extension_status(layout)

        self.assertTrue(result.ok)
        self.assertEqual(status.state, STATE_READY)
        self.assertTrue(status.facts["audit"]["ok"])
        self.assertEqual(status.facts["plan"]["source_commit"], "abc123")

    def test_install_environment_marks_broken_when_audit_fails(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            source = self._make_source(project)
            self._make_constraints(project)
            layout = ExtensionLayout(project / "extensions" / "anima_lora")
            plan = build_environment_install_plan(project, layout, source, dry_run=False)

            discovered_python = plan.python_install_dir / "cpython-3.13.99-windows-x86_64-none" / "python.exe"

            def fake_run(command, cwd, log, env=None, retries=0):
                if len(command) >= 3 and command[0] == str(discovered_python) and command[1:3] == ["-m", "venv"]:
                    plan.venv_python.parent.mkdir(parents=True)
                    plan.venv_python.write_text("", encoding="utf-8")
                if len(command) >= 3 and command[1:3] == ["python", "install"]:
                    discovered_python.parent.mkdir(parents=True)
                    discovered_python.write_text("", encoding="utf-8")

            with mock.patch("mikazuki.anima_fast_backend.environment._uv_command", return_value="uv"), \
                mock.patch("mikazuki.anima_fast_backend.environment._run_streaming", side_effect=fake_run), \
                mock.patch(
                    "mikazuki.anima_fast_backend.environment.audit_environment",
                    return_value=AuditResult(ok=False, errors=["missing flash-attn"]),
                ):
                result = install_environment(plan, lambda _line: None)

            status = read_extension_status(layout)

        self.assertFalse(result.ok)
        self.assertEqual(status.state, STATE_BROKEN)
        self.assertIn("missing flash-attn", status.reason)

    def test_run_streaming_retries_transient_failures(self):
        calls = {"count": 0}
        lines: list[str] = []

        def fake_once(command, cwd, log, env=None):
            calls["count"] += 1
            if calls["count"] == 1:
                raise subprocess.CalledProcessError(1, command)
            log("[fake] ok")

        with tempfile.TemporaryDirectory() as td, \
            mock.patch("mikazuki.anima_fast_backend.environment._run_streaming_once", side_effect=fake_once), \
            mock.patch("mikazuki.anima_fast_backend.environment.time.sleep"):
            _run_streaming(["uv", "pip", "install"], Path(td), lines.append, retries=2)

        self.assertEqual(calls["count"], 2)
        self.assertTrue(any("[retry]" in line for line in lines))

    def test_audit_environment_detects_anima_missing_dependency(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            layout = ExtensionLayout(project / "extensions" / "anima_lora")
            layout.source.mkdir(parents=True)
            layout.train_py.write_text("", encoding="utf-8")
            layout.venv_python.parent.mkdir(parents=True)
            layout.venv_python.write_text("", encoding="utf-8")

            with mock.patch(
                "mikazuki.anima_fast_backend.environment._collect_python_facts",
                return_value={
                    "python": str(layout.venv_python),
                    "version": "3.13.13",
                    "prefix": str(layout.venv_python.parent.parent),
                    "base_prefix": str(project / ".python"),
                    "packages": {"torch": None},
                    "imports": {"flash_attn": "ModuleNotFoundError"},
                    "torch_cuda_available": False,
                },
            ), mock.patch(
                "mikazuki.anima_fast_backend.environment._main_facts_in_process",
                return_value={
                    "python": str(project / ".venv" / "Scripts" / "python.exe"),
                    "version": "3.12.13",
                    "prefix": str(project / ".venv"),
                    "base_prefix": str(project / ".python"),
                    "packages": {
                        "numpy": "1.26.4",
                        "opencv-python": "4.8.1.78",
                        "torch": "2.11.0+cu130",
                        "torchvision": "0.26.0+cu130",
                    },
                    "imports": {"cv2": True, "torch": True},
                },
            ):
                result = audit_environment(project, layout, require_cuda=True)

        self.assertFalse(result.ok)
        self.assertTrue(any("flash_attn" in error or "torch.cuda" in error for error in result.errors))

    def test_interrupted_install_marks_broken_and_retry_can_repair(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            source = self._make_source(project)
            self._make_constraints(project)
            layout = ExtensionLayout(project / "extensions" / "anima_lora")
            attempts = {"count": 0}

            def fake_install(plan, log):
                attempts["count"] += 1
                layout.source.mkdir(parents=True, exist_ok=True)
                layout.train_py.write_text("print('train')\n", encoding="utf-8")
                layout.venv_python.parent.mkdir(parents=True, exist_ok=True)
                layout.venv_python.write_text("", encoding="utf-8")
                if attempts["count"] == 1:
                    raise KeyboardInterrupt("simulated interrupt")
                from mikazuki.anima_fast_backend.extension_state import write_install_state

                write_install_state(layout, STATE_READY, {"audit": {"ok": True}, "attempt": attempts["count"]})
                return AuditResult(ok=True)

            with mock.patch("mikazuki.anima_fast_backend.environment.install_environment", side_effect=fake_install):
                first_id, _ = start_install_task(project, layout, source, dry_run=False)
                first_task = tm.tasks[first_id]
                first_task.lock.acquire()
                first_task.lock.release()
                import time

                deadline = time.time() + 2
                while first_task.status.name not in {"FINISHED", "FAILED"} and time.time() < deadline:
                    time.sleep(0.01)

                self.assertEqual(first_task.status.name, "FAILED")
                self.assertEqual(first_task.returncode, 1)
                self.assertEqual(read_extension_status(layout).state, STATE_BROKEN)

                second_id, _ = start_install_task(project, layout, source, dry_run=False)
                second_task = tm.tasks[second_id]
                deadline = time.time() + 2
                while second_task.status.name not in {"FINISHED", "FAILED"} and time.time() < deadline:
                    time.sleep(0.01)

                self.assertEqual(second_task.status.name, "FINISHED")
                self.assertEqual(second_task.returncode, 0)
                self.assertEqual(read_extension_status(layout).state, STATE_READY)


    def test_anima_constraints_include_optimizer_packages(self):
        constraints = Path(__file__).resolve().parents[1] / "config" / "anima_fast_environment" / "anima-constraints-cu130.txt"
        text = constraints.read_text(encoding="utf-8")
        for package in ("bitsandbytes==0.49.2", "dadaptation==3.1", "lion-pytorch==0.2.3", "prodigyopt==1.1.2"):
            self.assertIn(package, text)


if __name__ == "__main__":
    unittest.main()

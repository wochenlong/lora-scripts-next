from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import subprocess

from mikazuki.anima_fast_backend.environment import (
    ANIMA_OPTIMIZER_PACKAGES,
    AuditResult,
    anima_pip_dependency_targets,
    audit_environment,
    build_environment_install_plan,
    install_environment,
    localize_linux_flash_attn_dependency,
    _run_streaming,
    start_install_task,
)
from mikazuki.anima_fast_backend.extension_state import (
    STATE_BROKEN,
    STATE_INSTALLING,
    STATE_INSTALLED_UNVERIFIED,
    STATE_READY,
    ExtensionLayout,
    read_extension_status,
    write_install_state,
)
from mikazuki.tasks import Task, tm


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

    def test_install_plan_uses_linux_python_layout_off_windows(self):
        with tempfile.TemporaryDirectory() as td, mock.patch(
            "mikazuki.anima_fast_backend.environment.sys.platform", "linux"
        ):
            project = Path(td)
            source = self._make_source(project)
            layout = ExtensionLayout(project / "extensions" / "anima_lora")

            plan = build_environment_install_plan(project, layout, source)

        self.assertTrue(str(plan.base_python).replace("\\", "/").endswith("cpython-3.13.13-linux-x86_64-gnu/bin/python3"))
        self.assertTrue(str(plan.venv_python).replace("\\", "/").endswith("extensions/anima_lora/.venv/bin/python"))

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

    def test_anima_constraints_scope_linux_fast_runtime_packages_by_platform(self):
        constraints = Path(__file__).resolve().parents[1] / "config" / "anima_fast_environment" / "anima-constraints-cu130.txt"
        text = constraints.read_text(encoding="utf-8")

        self.assertIn('torch==2.11.0+cu130 ; sys_platform == "win32"', text)
        self.assertIn('torchvision==0.26.0+cu130 ; sys_platform == "win32"', text)
        self.assertIn('torch==2.12.0+cu130 ; sys_platform == "linux"', text)
        self.assertIn('torchvision==0.27.0+cu130 ; sys_platform == "linux"', text)
        self.assertIn('triton-windows==3.7.0.post26 ; sys_platform == "win32"', text)

    def test_anima_expected_packages_skip_triton_windows_on_linux(self):
        from mikazuki.anima_fast_backend.environment import _anima_expected_for_platform

        linux_expected = _anima_expected_for_platform("linux")
        windows_expected = _anima_expected_for_platform("win32")

        self.assertEqual(linux_expected["exact"]["torch"], "2.12.0+cu130")
        self.assertEqual(linux_expected["exact"]["torchvision"], "0.27.0+cu130")
        self.assertNotIn("triton-windows", linux_expected["exact"])
        self.assertEqual(windows_expected["exact"]["torch"], "2.11.0+cu130")
        self.assertEqual(windows_expected["exact"]["torchvision"], "0.26.0+cu130")
        self.assertEqual(windows_expected["exact"]["triton-windows"], "3.7.0.post26")

    def test_anima_overrides_use_headless_opencv_on_linux(self):
        overrides = Path(__file__).resolve().parents[1] / "config" / "anima_fast_environment" / "anima-overrides-cu130.txt"
        text = overrides.read_text(encoding="utf-8")

        self.assertIn('opencv-python-headless==4.13.0.92 ; sys_platform == "linux"', text)

    def test_localize_linux_flash_attn_dependency_uses_cu130_direct_url(self):
        with tempfile.TemporaryDirectory() as td, mock.patch(
            "mikazuki.anima_fast_backend.environment.sys.platform", "linux"
        ):
            source = Path(td) / "source"
            source.mkdir()
            pyproject = source / "pyproject.toml"
            pyproject.write_text(
                '[project]\ndependencies = [\n'
                '    "flash-attn @ https://example.invalid/linux-cu132.whl ; sys_platform == \'linux\'",\n'
                '    "flash-attn @ https://example.invalid/windows.whl ; sys_platform == \'win32\'",\n'
                ']\n',
                encoding="utf-8",
            )
            lines: list[str] = []

            changed = localize_linux_flash_attn_dependency(source, lines.append)
            text = pyproject.read_text(encoding="utf-8")

        self.assertEqual(len(changed), 1)
        self.assertIn("flash_attn-2.8.3%2Bcu130torch2.11-cp313-cp313-linux_x86_64.whl", text)
        self.assertIn("windows.whl", text)
        self.assertTrue(any("localized Linux cu130 flash-attn" in line for line in lines))

    def test_audit_environment_skips_triton_windows_on_linux(self):
        with tempfile.TemporaryDirectory() as td, mock.patch(
            "mikazuki.anima_fast_backend.environment.sys.platform", "linux"
        ):
            project = Path(td)
            layout = ExtensionLayout(project / "extensions" / "anima_lora")
            layout.source.mkdir(parents=True)
            layout.train_py.write_text("", encoding="utf-8")
            layout.venv_python.parent.mkdir(parents=True)
            layout.venv_python.write_text("", encoding="utf-8")

            def fake_collect(python, packages, imports, cwd):
                package_facts = {name: "unused" for name in packages}
                package_facts.update(
                    {
                        "torch": "2.12.0+cu130",
                        "torchvision": "0.27.0+cu130",
                        "flash-attn": "2.8.3+cu130torch2.11",
                        "transformers": "5.9.0",
                        "diffusers": "0.37.1",
                        "accelerate": "1.13.0",
                        "safetensors": "0.7.0",
                        "iopath": "0.1.10",
                        "bitsandbytes": "0.49.2",
                        "dadaptation": "3.1",
                    }
                )
                return {
                    "python": str(python),
                    "version": "3.13.13",
                    "prefix": str(layout.venv_python.parent.parent),
                    "base_prefix": str(project / ".python"),
                    "packages": package_facts,
                    "imports": {name: True for name in imports},
                    "torch_cuda_available": True,
                }

            with mock.patch("mikazuki.anima_fast_backend.environment._collect_python_facts", side_effect=fake_collect), \
                mock.patch(
                    "mikazuki.anima_fast_backend.environment._main_facts_in_process",
                    return_value={
                        "python": str(project / ".venv" / "bin" / "python"),
                        "version": "3.13.13",
                        "prefix": str(project / ".venv"),
                        "base_prefix": str(project / ".python"),
                        "packages": {"numpy": "1.26.4", "opencv-python": None, "opencv-python-headless": "4.8.1.78"},
                        "imports": {"cv2": True, "torch": True},
                    },
                ):
                result = audit_environment(project, layout, require_cuda=True)

        self.assertTrue(result.ok, result.errors)
        self.assertNotIn("triton-windows", result.facts["anima"]["packages"])

    def test_anima_pip_dependency_targets_include_optimizer_and_quanto(self):
        targets = anima_pip_dependency_targets()
        for name, version in ANIMA_OPTIMIZER_PACKAGES.items():
            self.assertIn(f"{name}=={version}", targets)
        self.assertIn("optimum-quanto>=0.2.0", targets)

    def test_install_environment_pip_install_includes_explicit_optimizer_targets(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            source = self._make_source(project)
            self._make_constraints(project)
            layout = ExtensionLayout(project / "extensions" / "anima_lora")
            plan = build_environment_install_plan(project, layout, source, dry_run=False)
            discovered_python = plan.python_install_dir / "cpython-3.13.99-windows-x86_64-none" / "python.exe"
            pip_commands: list[list[str]] = []

            def fake_run(command, cwd, log, env=None, retries=0):
                if len(command) >= 3 and command[0] == str(discovered_python) and command[1:3] == ["-m", "venv"]:
                    plan.venv_python.parent.mkdir(parents=True)
                    plan.venv_python.write_text("", encoding="utf-8")
                if len(command) >= 3 and command[1:3] == ["python", "install"]:
                    discovered_python.parent.mkdir(parents=True)
                    discovered_python.write_text("", encoding="utf-8")
                if len(command) >= 3 and command[1:3] == ["pip", "install"]:
                    pip_commands.append(list(command))

            with mock.patch("mikazuki.anima_fast_backend.environment._uv_command", return_value="uv"), \
                mock.patch("mikazuki.anima_fast_backend.environment.copy_source_snapshot"), \
                mock.patch("mikazuki.anima_fast_backend.environment._run_streaming", side_effect=fake_run), \
                mock.patch(
                    "mikazuki.anima_fast_backend.environment.audit_environment",
                    return_value=AuditResult(ok=True),
                ):
                install_environment(plan, lambda _line: None)

        self.assertEqual(len(pip_commands), 1)
        pip_cmd = pip_commands[0]
        self.assertIn("bitsandbytes==0.49.2", pip_cmd)
        self.assertIn("dadaptation==3.1", pip_cmd)
        self.assertIn("optimum-quanto>=0.2.0", pip_cmd)
        self.assertEqual(pip_cmd[-1], str(layout.source))

    def test_stale_installing_without_task_marks_broken(self):
        with tempfile.TemporaryDirectory() as td:
            layout = ExtensionLayout(Path(td) / "extensions" / "anima_lora")
            layout.source.mkdir(parents=True)
            layout.train_py.write_text("", encoding="utf-8")
            layout.venv_python.parent.mkdir(parents=True)
            layout.venv_python.write_text("", encoding="utf-8")
            write_install_state(layout, STATE_INSTALLING, {"task_id": "missing-anima-install-task"})

            status = read_extension_status(layout)

        self.assertEqual(status.state, STATE_BROKEN)
        self.assertIn("no longer active", status.reason)

    def test_stale_installing_reconciles_ready_when_task_finished_and_audit_ok(self):
        task_id = "anima-install-reconcile-test"
        with tempfile.TemporaryDirectory() as td:
            layout = ExtensionLayout(Path(td) / "extensions" / "anima_lora")
            layout.source.mkdir(parents=True)
            layout.train_py.write_text("", encoding="utf-8")
            layout.venv_python.parent.mkdir(parents=True)
            layout.venv_python.write_text("", encoding="utf-8")
            audit = {"ok": True, "errors": [], "warnings": [], "facts": {}}
            layout.audit_result.write_text(json.dumps(audit), encoding="utf-8")
            write_install_state(layout, STATE_INSTALLING, {"task_id": task_id})
            task = Task(task_id, ["noop"])
            task.finish_log_only(0)
            tm.add_task(task_id, task)

            status = read_extension_status(layout)

        self.assertEqual(status.state, STATE_READY)
        self.assertTrue(status.facts.get("audit", {}).get("ok"))

    def test_start_install_resolves_source_root_on_frozen_plan(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            source = self._make_source(project)
            self._make_constraints(project)
            layout = ExtensionLayout(project / "extensions" / "anima_lora")
            cache = project / ".cache" / "anima_fast" / "upstream"
            cache.mkdir(parents=True)
            (cache / "train.py").write_text("print('cached')\n", encoding="utf-8")
            captured: dict = {}

            def fake_install(plan, log):
                captured["source_root"] = plan.source_root
                from mikazuki.anima_fast_backend.extension_state import write_install_state

                write_install_state(layout, STATE_READY, {"audit": {"ok": True}})
                return AuditResult(ok=True)

            def fake_ensure(project_root, preferred, commit, log=None):
                return cache.resolve()

            with mock.patch(
                "mikazuki.anima_fast_backend.source_root.ensure_install_source_ready",
                side_effect=fake_ensure,
            ):
                with mock.patch(
                    "mikazuki.anima_fast_backend.environment.install_environment",
                    side_effect=fake_install,
                ):
                    task_id, _ = start_install_task(project, layout, source, dry_run=False)
                    task = tm.tasks[task_id]
                    import time

                    deadline = time.time() + 3
                    while task.status.name not in {"FINISHED", "FAILED"} and time.time() < deadline:
                        time.sleep(0.02)

            self.assertEqual(task.status.name, "FINISHED")
            self.assertEqual(task.returncode, 0)
            self.assertEqual(captured.get("source_root"), cache.resolve())


if __name__ == "__main__":
    unittest.main()

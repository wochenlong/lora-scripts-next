from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import subprocess

from mikazuki.anima_fast_backend.environment import (
    ANIMA_OPTIMIZER_PACKAGES,
    AuditResult,
    _collect_python_facts,
    _find_base_python,
    _run_streaming_once,
    anima_pip_dependency_targets,
    audit_environment,
    build_environment_install_plan,
    install_environment,
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


def _fake_discovered_python(plan) -> Path:
    if sys.platform == "win32":
        return plan.python_install_dir / "cpython-3.13.99-windows-x86_64-none" / "python.exe"
    return plan.python_install_dir / "cpython-3.13.99-linux-x86_64-gnu" / "bin" / "python3"


class AnimaFastEnvironmentInstallerTests(unittest.TestCase):
    def _make_runtime_source(self, layout: ExtensionLayout) -> None:
        layout.source.mkdir(parents=True, exist_ok=True)
        layout.train_py.write_text("print('train')\n", encoding="utf-8")
        (layout.source / "configs").mkdir(exist_ok=True)
        (layout.source / "configs" / "base.toml").write_text("", encoding="utf-8")
        (layout.source / "scripts" / "preprocess").mkdir(parents=True, exist_ok=True)
        (layout.source / "scripts" / "preprocess" / "resize_images.py").write_text("", encoding="utf-8")
        weights_dir = layout.source / "library" / "anima"
        weights_dir.mkdir(parents=True, exist_ok=True)
        (weights_dir / "weights.py").write_text(
            'def _strip_net_prefix(key: str) -> str:\n'
            '    return key[len("net.") :] if key.startswith("net.") else key\n',
            encoding="utf-8",
        )

    def _make_source(self, root: Path) -> Path:
        source = root / "anima_source"
        source.mkdir()
        (source / "train.py").write_text("print('train')", encoding="utf-8")
        (source / "pyproject.toml").write_text("[project]\nname='anima-test'\n", encoding="utf-8")
        (source / "configs").mkdir()
        (source / "configs" / "base.toml").write_text("", encoding="utf-8")
        (source / "scripts" / "preprocess").mkdir(parents=True)
        (source / "scripts" / "preprocess" / "resize_images.py").write_text("", encoding="utf-8")
        weights_dir = source / "library" / "anima"
        weights_dir.mkdir(parents=True)
        (weights_dir / "weights.py").write_text(
            'def _strip_net_prefix(key: str) -> str:\n'
            '    return key[len("net.") :] if key.startswith("net.") else key\n',
            encoding="utf-8",
        )
        return source

    def _make_constraints(self, project: Path) -> None:
        env_dir = project / "config" / "anima_fast_environment"
        env_dir.mkdir(parents=True)
        (env_dir / "anima-constraints-cu132.txt").write_text("torch==2.12.0+cu132\n", encoding="utf-8")
        (env_dir / "anima-overrides-cu132.txt").write_text("numpy>=2\n", encoding="utf-8")

    def test_install_plan_uses_linux_python_layout_off_windows(self):
        with tempfile.TemporaryDirectory() as td, mock.patch(
            "mikazuki.anima_fast_backend.environment.sys.platform", "linux"
        ), mock.patch(
            "mikazuki.anima_fast_backend.environment.platform_module.machine",
            return_value="x86_64",
        ):
            project = Path(td)
            source = self._make_source(project)
            layout = ExtensionLayout(project / "extensions" / "anima_lora")

            plan = build_environment_install_plan(project, layout, source)

        self.assertTrue(str(plan.base_python).replace("\\", "/").endswith("cpython-3.13.13-linux-x86_64-gnu/bin/python3"))
        self.assertTrue(str(plan.venv_python).replace("\\", "/").endswith("extensions/anima_lora/.venv/bin/python"))

    def test_install_plan_uses_linux_aarch64_python_layout(self):
        with tempfile.TemporaryDirectory() as td, \
            mock.patch("mikazuki.anima_fast_backend.environment.sys.platform", "linux"), \
            mock.patch(
                "mikazuki.anima_fast_backend.environment.platform_module.machine",
                return_value="aarch64",
            ):
            project = Path(td)
            source = self._make_source(project)
            layout = ExtensionLayout(project / "extensions" / "anima_lora")

            plan = build_environment_install_plan(project, layout, source)

        self.assertTrue(
            str(plan.base_python).replace("\\", "/").endswith(
                "cpython-3.13.13-linux-aarch64-gnu/bin/python3"
            )
        )

    def test_find_base_python_filters_linux_fallback_by_architecture(self):
        with tempfile.TemporaryDirectory() as td, \
            mock.patch("mikazuki.anima_fast_backend.environment.sys.platform", "linux"), \
            mock.patch(
                "mikazuki.anima_fast_backend.environment.platform_module.machine",
                return_value="aarch64",
            ):
            project = Path(td)
            source = self._make_source(project)
            layout = ExtensionLayout(project / "extensions" / "anima_lora")
            plan = build_environment_install_plan(project, layout, source)
            x64_python = (
                plan.python_install_dir
                / "cpython-3.13.99-linux-x86_64-gnu"
                / "bin"
                / "python3"
            )
            arm_python = (
                plan.python_install_dir
                / "cpython-3.13.98-linux-aarch64-gnu"
                / "bin"
                / "python3"
            )
            x64_python.parent.mkdir(parents=True)
            x64_python.write_text("", encoding="utf-8")
            arm_python.parent.mkdir(parents=True)
            arm_python.write_text("", encoding="utf-8")

            discovered = _find_base_python(plan)

        self.assertEqual(discovered, arm_python.resolve())

    def test_install_plan_rejects_unsupported_runtime_platform(self):
        with tempfile.TemporaryDirectory() as td, \
            mock.patch("mikazuki.anima_fast_backend.environment.sys.platform", "darwin"), \
            mock.patch(
                "mikazuki.anima_fast_backend.environment.platform_module.machine",
                return_value="arm64",
            ):
            project = Path(td)
            source = self._make_source(project)
            layout = ExtensionLayout(project / "extensions" / "anima_lora")

            with self.assertRaisesRegex(
                RuntimeError,
                "Windows x86_64.*Linux x86_64.*Linux aarch64",
            ):
                build_environment_install_plan(project, layout, source)

    def test_source_snapshot_includes_anima_lora_package(self):
        from mikazuki.anima_fast_backend.installer import build_install_plan, copy_source_snapshot

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = self._make_source(root)
            (source / "anima_lora").mkdir()
            (source / "anima_lora" / "__init__.py").write_text("", encoding="utf-8")
            layout = ExtensionLayout(root / "extensions" / "anima_lora")

            copy_source_snapshot(build_install_plan(source, layout, dry_run=False))
            copied = (layout.source / "anima_lora" / "__init__.py").is_file()

        self.assertTrue(copied)

    def test_linux_aarch64_launch_sets_bitsandbytes_cuda_compatibility(self):
        from mikazuki.anima_fast_backend.launcher import build_launch_spec
        from mikazuki.anima_fast_backend.settings import RuntimeConfig

        with tempfile.TemporaryDirectory() as td, \
            mock.patch("mikazuki.anima_fast_backend.launcher.platform.system", return_value="Linux"), \
            mock.patch("mikazuki.anima_fast_backend.launcher.platform.machine", return_value="aarch64"):
            root = Path(td)
            runtime = RuntimeConfig(
                anima_root=root / "extensions" / "anima_lora" / "source",
                python=root / "extensions" / "anima_lora" / ".venv" / "bin" / "python",
                lora_next_root=root,
                output_dir=root / "output",
                logging_dir=root / "logs",
                cache_dir=root / ".cache",
            )
            config = root / "config.toml"
            config.write_text("", encoding="utf-8")

            spec = build_launch_spec(runtime, config, "run-1")

        self.assertEqual(spec.env["BNB_CUDA_VERSION"], "130")

    def test_resize_uses_v1171_script_and_target_res_argument(self):
        from mikazuki.anima_fast_backend.preprocess import run_resize_images
        from mikazuki.anima_fast_backend.settings import RuntimeConfig

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            anima_root = root / "source"
            script = anima_root / "scripts" / "preprocess" / "resize_images.py"
            script.parent.mkdir(parents=True)
            script.write_text("", encoding="utf-8")
            source = root / "dataset"
            source.mkdir()
            runtime = RuntimeConfig(
                anima_root=anima_root,
                python=root / "python",
                lora_next_root=root,
                output_dir=root / "output",
                logging_dir=root / "logs",
                cache_dir=root / ".cache",
            )

            with mock.patch(
                "mikazuki.anima_fast_backend.preprocess.subprocess.run",
                return_value=mock.Mock(returncode=0),
            ) as run:
                run_resize_images(runtime, source, root / "resized", 1024)

        command = run.call_args.args[0]
        self.assertEqual(command[1], str(script))
        self.assertIn("--target_res", command)
        self.assertNotIn("--resolution", command)

    def test_ready_requires_audit_ok_facts(self):
        with tempfile.TemporaryDirectory() as td:
            layout = ExtensionLayout(Path(td) / "extensions" / "anima_lora")
            self._make_runtime_source(layout)
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

            discovered_python = _fake_discovered_python(plan)

            def fake_run(command, cwd, log, env=None, retries=0):
                if len(command) >= 3 and command[0] == str(discovered_python) and command[1:3] == ["-m", "venv"]:
                    plan.venv_python.parent.mkdir(parents=True)
                    plan.venv_python.write_text("", encoding="utf-8")
                if len(command) >= 3 and command[1:3] == ["python", "install"]:
                    discovered_python.parent.mkdir(parents=True)
                    discovered_python.write_text("", encoding="utf-8")
                log("[fake] command completed")

            def fake_copy(_plan):
                self._make_runtime_source(layout)

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

            discovered_python = _fake_discovered_python(plan)

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

    def test_audit_subprocess_sets_bitsandbytes_cuda_version_on_linux_aarch64(self):
        captured: dict = {}

        def fake_run(*args, **kwargs):
            captured["env"] = kwargs["env"]
            return mock.Mock(
                returncode=0,
                stdout='{"python": "python", "packages": {}, "imports": {}}\n',
                stderr="",
            )

        with tempfile.TemporaryDirectory() as td, \
            mock.patch("mikazuki.anima_fast_backend.environment.sys.platform", "linux"), \
            mock.patch(
                "mikazuki.anima_fast_backend.environment.platform_module.machine",
                return_value="aarch64",
            ), \
            mock.patch(
                "mikazuki.anima_fast_backend.environment.subprocess.run",
                side_effect=fake_run,
            ):
            _collect_python_facts(
                Path("python"),
                packages=[],
                imports=[],
                cwd=Path(td),
            )

        self.assertEqual(captured["env"]["BNB_CUDA_VERSION"], "130")

    def test_audit_environment_detects_anima_missing_dependency(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            layout = ExtensionLayout(project / "extensions" / "anima_lora")
            self._make_runtime_source(layout)
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

            def fake_install(plan, log, task_id=None, progress=None):
                attempts["count"] += 1
                self._make_runtime_source(layout)
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
        constraints = Path(__file__).resolve().parents[1] / "config" / "anima_fast_environment" / "anima-constraints-cu132.txt"
        text = constraints.read_text(encoding="utf-8")
        for package in ("bitsandbytes==0.49.2", "dadaptation==3.1", "lion-pytorch==0.2.3", "prodigyopt==1.1.2"):
            self.assertIn(package, text)

    def test_anima_constraints_pin_cuda_132_runtime(self):
        constraints = Path(__file__).resolve().parents[1] / "config" / "anima_fast_environment" / "anima-constraints-cu132.txt"
        text = constraints.read_text(encoding="utf-8")

        self.assertIn("torch==2.12.0+cu132", text)
        self.assertIn("torchvision==0.27.0+cu132", text)
        self.assertIn('triton-windows==3.7.0.post26 ; sys_platform == "win32"', text)
        self.assertIn("transformers==5.10.1", text)
        self.assertIn("diffusers==0.39.0", text)
        self.assertIn("safetensors==0.8.0", text)

    def test_anima_expected_packages_skip_triton_windows_on_linux(self):
        from mikazuki.anima_fast_backend.environment import _anima_expected_for_platform

        linux_expected = _anima_expected_for_platform("linux")
        windows_expected = _anima_expected_for_platform("win32")

        self.assertEqual(linux_expected["exact"]["torch"], "2.12.0+cu132")
        self.assertEqual(linux_expected["exact"]["torchvision"], "0.27.0+cu132")
        self.assertNotIn("triton-windows", linux_expected["exact"])
        self.assertEqual(windows_expected["exact"]["torch"], "2.12.0+cu132")
        self.assertEqual(windows_expected["exact"]["torchvision"], "0.27.0+cu132")
        self.assertEqual(windows_expected["exact"]["triton-windows"], "3.7.0.post26")

    def test_anima_overrides_use_headless_opencv_on_linux(self):
        overrides = Path(__file__).resolve().parents[1] / "config" / "anima_fast_environment" / "anima-overrides-cu132.txt"
        text = overrides.read_text(encoding="utf-8")

        self.assertIn('opencv-python-headless==4.13.0.92 ; sys_platform == "linux"', text)

    def test_flash_attn_targets_cover_windows_and_linux_architectures(self):
        from mikazuki.anima_fast_backend.environment import flash_attn_dependency_target

        windows = flash_attn_dependency_target("win32", "AMD64")
        linux_x64 = flash_attn_dependency_target("linux", "x86_64")
        linux_arm = flash_attn_dependency_target("linux", "aarch64")

        self.assertIn("cu132torch2.12", windows)
        self.assertIn("win_amd64", windows)
        self.assertIn("linux_x86_64", linux_x64)
        self.assertIn("linux_aarch64", linux_arm)
        self.assertIsNone(flash_attn_dependency_target("darwin", "arm64"))

    def test_patch_comfyui_checkpoint_prefix_is_idempotent(self):
        from mikazuki.anima_fast_backend.environment import patch_comfyui_checkpoint_prefix

        with tempfile.TemporaryDirectory() as td:
            source = self._make_source(Path(td))
            first = patch_comfyui_checkpoint_prefix(source, lambda _line: None)
            second = patch_comfyui_checkpoint_prefix(source, lambda _line: None)
            namespace: dict = {}
            weights = source / "library" / "anima" / "weights.py"
            exec(compile(weights.read_text(encoding="utf-8"), "weights.py", "exec"), namespace)

        self.assertTrue(first)
        self.assertEqual(second, [])
        self.assertEqual(namespace["_strip_net_prefix"]("net.blocks.0.x"), "blocks.0.x")
        self.assertEqual(namespace["_strip_net_prefix"]("model.diffusion_model.blocks.0.x"), "blocks.0.x")

    def test_patch_comfyui_checkpoint_prefix_skips_upstream_support(self):
        from mikazuki.anima_fast_backend.environment import patch_comfyui_checkpoint_prefix

        with tempfile.TemporaryDirectory() as td:
            source = self._make_source(Path(td))
            weights = source / "library" / "anima" / "weights.py"
            upstream_text = (
                '_DIT_PREFIXES = ("net.", "model.diffusion_model.")\n'
                'def _strip_net_prefix(key: str) -> str:\n'
                '    for prefix in _DIT_PREFIXES:\n'
                '        if key.startswith(prefix):\n'
                '            return key[len(prefix):]\n'
                '    return key\n'
            )
            weights.write_text(upstream_text, encoding="utf-8")

            applied = patch_comfyui_checkpoint_prefix(source, lambda _line: None)
            preserved = weights.read_text(encoding="utf-8")

        self.assertEqual(applied, [])
        self.assertEqual(preserved, upstream_text)

    def test_install_streaming_defaults_hf_endpoint_mirror(self):
        from mikazuki.anima_fast_backend.environment import _run_streaming_once, DEFAULT_HF_ENDPOINT

        captured: dict = {}

        class _FakeStdout:
            def readline(self):
                return ""

        class _FakeProc:
            def __init__(self, *a, **k):
                self.stdout = _FakeStdout()
                captured["env"] = k.get("env")

            def wait(self):
                return 0

        env_without_endpoint = {k: v for k, v in os.environ.items() if k != "HF_ENDPOINT"}
        with tempfile.TemporaryDirectory() as td, \
            mock.patch("mikazuki.anima_fast_backend.environment.subprocess.Popen", _FakeProc), \
            mock.patch.dict("os.environ", env_without_endpoint, clear=True):
            _run_streaming_once(["echo", "hi"], Path(td), lambda _l: None)

        self.assertEqual(captured["env"].get("HF_ENDPOINT"), DEFAULT_HF_ENDPOINT)

    def test_install_streaming_respects_user_hf_endpoint(self):
        from mikazuki.anima_fast_backend.environment import _run_streaming_once

        captured: dict = {}

        class _FakeStdout:
            def readline(self):
                return ""

        class _FakeProc:
            def __init__(self, *a, **k):
                self.stdout = _FakeStdout()
                captured["env"] = k.get("env")

            def wait(self):
                return 0

        with tempfile.TemporaryDirectory() as td, \
            mock.patch("mikazuki.anima_fast_backend.environment.subprocess.Popen", _FakeProc), \
            mock.patch.dict("os.environ", {"HF_ENDPOINT": "https://modelscope.cn"}, clear=False):
            _run_streaming_once(["echo", "hi"], Path(td), lambda _l: None)

        self.assertEqual(captured["env"].get("HF_ENDPOINT"), "https://modelscope.cn")

    def test_install_streaming_emits_heartbeat_when_command_is_silent(self):
        lines: list[str] = []
        with tempfile.TemporaryDirectory() as td:
            _run_streaming_once(
                [sys.executable, "-c", "import time; time.sleep(0.5)"],
                Path(td),
                lines.append,
                heartbeat_seconds=0.1,
            )

        self.assertTrue(any(line.startswith("[wait]") for line in lines))
        self.assertIn("[exit] returncode=0", lines)

    def test_install_streaming_reaps_live_process_before_propagating_callback_errors(self):
        for failure_source in ("reader", "log"):
            with self.subTest(failure_source=failure_source):
                original_error = (
                    OSError("simulated read failure")
                    if failure_source == "reader"
                    else ValueError("simulated log failure")
                )
                events = []
                process_holder = {}

                class _FakeStdout:
                    def __init__(self):
                        self.reads = 0

                    def readline(self):
                        if failure_source == "reader":
                            raise original_error
                        self.reads += 1
                        return "output\n" if self.reads == 1 else ""

                class _LiveProcess:
                    def __init__(self, *args, **kwargs):
                        self.stdout = _FakeStdout()
                        self.killed = False
                        self.reaped = False
                        process_holder["process"] = self

                    def poll(self):
                        return None if not self.reaped else -9

                    def terminate(self):
                        events.append("terminate")

                    def kill(self):
                        events.append("kill")
                        self.killed = True

                    def wait(self, timeout=None):
                        events.append(("wait", timeout))
                        if not self.killed:
                            if timeout is None:
                                raise AssertionError(
                                    "blocking wait called while subprocess is still alive"
                                )
                            raise subprocess.TimeoutExpired(["uv"], timeout)
                        self.reaped = True
                        return -9

                def log(line):
                    if failure_source == "log" and line == "output":
                        raise original_error

                with tempfile.TemporaryDirectory() as td, mock.patch(
                    "mikazuki.anima_fast_backend.environment.subprocess.Popen",
                    _LiveProcess,
                ):
                    with self.assertRaises(type(original_error)) as raised:
                        _run_streaming_once(
                            ["uv", "pip", "install"],
                            Path(td),
                            log,
                            heartbeat_seconds=0.01,
                        )

                self.assertIs(raised.exception, original_error)
                self.assertEqual(events[0], "terminate")
                self.assertIsNotNone(events[1][1])
                self.assertEqual(events[2:], ["kill", ("wait", None)])
                self.assertTrue(process_holder["process"].reaped)

    def test_install_streaming_uses_windows_system_certificates_by_default(self):
        from mikazuki.anima_fast_backend.environment import _run_streaming_once

        captured: dict = {}

        class _FakeStdout:
            def readline(self):
                return ""

        class _FakeProc:
            def __init__(self, *a, **k):
                self.stdout = _FakeStdout()
                captured["env"] = k.get("env")

            def wait(self):
                return 0

        env_without_uv_certs = {
            key: value
            for key, value in os.environ.items()
            if key not in {"UV_SYSTEM_CERTS", "UV_NATIVE_TLS"}
        }
        with tempfile.TemporaryDirectory() as td, \
            mock.patch("mikazuki.anima_fast_backend.environment.subprocess.Popen", _FakeProc), \
            mock.patch("mikazuki.anima_fast_backend.environment.sys.platform", "win32"), \
            mock.patch.dict("os.environ", env_without_uv_certs, clear=True):
            _run_streaming_once(["uv", "pip", "install"], Path(td), lambda _line: None)

        self.assertEqual(captured["env"].get("UV_SYSTEM_CERTS"), "true")

    def test_install_streaming_explains_unknown_certificate_issuer(self):
        from mikazuki.anima_fast_backend.environment import _run_streaming_once

        lines = iter([
            "error sending request for url\n",
            "invalid peer certificate: UnknownIssuer\n",
        ])

        class _FakeStdout:
            def readline(self):
                return next(lines, "")

        class _FakeProc:
            def __init__(self, *a, **k):
                self.stdout = _FakeStdout()

            def wait(self):
                return 1

        logs: list[str] = []
        with tempfile.TemporaryDirectory() as td, \
            mock.patch("mikazuki.anima_fast_backend.environment.subprocess.Popen", _FakeProc):
            with self.assertRaises(subprocess.CalledProcessError):
                _run_streaming_once(["uv", "pip", "install"], Path(td), logs.append)

        self.assertTrue(any("UV_SYSTEM_CERTS=true" in line for line in logs))
        self.assertTrue(any("HTTPS" in line and "certificate" in line for line in logs))

    def test_audit_environment_skips_triton_windows_on_linux(self):
        with tempfile.TemporaryDirectory() as td, mock.patch(
            "mikazuki.anima_fast_backend.environment.sys.platform", "linux"
        ):
            project = Path(td)
            layout = ExtensionLayout(project / "extensions" / "anima_lora")
            self._make_runtime_source(layout)
            layout.venv_python.parent.mkdir(parents=True)
            layout.venv_python.write_text("", encoding="utf-8")

            def fake_collect(python, packages, imports, cwd):
                package_facts = {name: "unused" for name in packages}
                package_facts.update(
                    {
                        "torch": "2.12.0+cu132",
                        "torchvision": "0.27.0+cu132",
                        "flash-attn": "2.8.3+cu132torch2.12",
                        "transformers": "5.10.1",
                        "diffusers": "0.39.0",
                        "accelerate": "1.13.0",
                        "safetensors": "0.8.0",
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
        self.assertIn("iopath==0.1.10", targets)

    def test_anima_pip_dependency_targets_are_platform_aware(self):
        windows_targets = anima_pip_dependency_targets("win32")
        linux_targets = anima_pip_dependency_targets("linux")

        self.assertIn("triton-windows==3.7.0.post26", windows_targets)
        self.assertNotIn("triton-windows==3.7.0.post26", linux_targets)
        self.assertIn("opencv-python", windows_targets)
        self.assertIn("opencv-python-headless", linux_targets)
        for target in ("torch", "torchvision", "accelerate", "transformers", "diffusers"):
            self.assertIn(target, windows_targets)
            self.assertIn(target, linux_targets)

    def test_install_environment_uses_explicit_targets_and_uv_cache(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            source = self._make_source(project)
            self._make_constraints(project)
            layout = ExtensionLayout(project / "extensions" / "anima_lora")
            plan = build_environment_install_plan(project, layout, source, dry_run=False)
            self._make_runtime_source(layout)
            discovered_python = _fake_discovered_python(plan)
            commands: list[list[str]] = []
            pip_commands: list[list[str]] = []

            def fake_run(command, cwd, log, env=None, retries=0):
                commands.append(list(command))
                if len(command) >= 3 and command[0] == str(discovered_python) and command[1:3] == ["-m", "venv"]:
                    plan.venv_python.parent.mkdir(parents=True)
                    plan.venv_python.write_text("", encoding="utf-8")
                if len(command) >= 3 and command[1:3] == ["python", "install"]:
                    discovered_python.parent.mkdir(parents=True)
                    discovered_python.write_text("", encoding="utf-8")
                if len(command) >= 3 and command[1:3] == ["pip", "install"]:
                    pip_commands.append(list(command))

            with mock.patch("mikazuki.anima_fast_backend.environment._uv_command", return_value="uv"), \
                mock.patch(
                    "mikazuki.anima_fast_backend.environment.anima_pip_dependency_targets",
                    return_value=anima_pip_dependency_targets("win32"),
                ), \
                mock.patch("mikazuki.anima_fast_backend.environment.copy_source_snapshot"), \
                mock.patch("mikazuki.anima_fast_backend.environment._run_streaming", side_effect=fake_run), \
                mock.patch(
                    "mikazuki.anima_fast_backend.environment.audit_environment",
                    return_value=AuditResult(ok=True),
                ):
                install_environment(plan, lambda _line: None)

        self.assertEqual(len(pip_commands), 2)
        pip_cmd = pip_commands[0]
        self.assertIn("--verbose", pip_cmd)
        self.assertIn("bitsandbytes==0.49.2", pip_cmd)
        self.assertIn("dadaptation==3.1", pip_cmd)
        self.assertIn("optimum-quanto>=0.2.0", pip_cmd)
        self.assertIn("iopath==0.1.10", pip_cmd)
        self.assertIn("triton-windows==3.7.0.post26", pip_cmd)
        self.assertIn("torch", pip_cmd)
        self.assertIn("--no-deps", pip_commands[1])
        self.assertIn("--verbose", pip_commands[1])
        self.assertEqual(pip_commands[1][-1], str(layout.source))
        self.assertFalse(any("--no-cache" in command for command in commands))

    def test_install_environment_broken_progress_does_not_report_complete(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            source = self._make_source(project)
            self._make_constraints(project)
            layout = ExtensionLayout(project / "extensions" / "anima_lora")
            plan = build_environment_install_plan(project, layout, source, dry_run=False)
            self._make_runtime_source(layout)
            discovered_python = _fake_discovered_python(plan)
            progress_events: list[dict] = []

            def fake_run(command, cwd, log, env=None, retries=0):
                if len(command) >= 3 and command[0] == str(discovered_python) and command[1:3] == ["-m", "venv"]:
                    plan.venv_python.parent.mkdir(parents=True)
                    plan.venv_python.write_text("", encoding="utf-8")
                if len(command) >= 3 and command[1:3] == ["python", "install"]:
                    discovered_python.parent.mkdir(parents=True)
                    discovered_python.write_text("", encoding="utf-8")

            with mock.patch("mikazuki.anima_fast_backend.environment._uv_command", return_value="uv"), \
                mock.patch("mikazuki.anima_fast_backend.environment.copy_source_snapshot"), \
                mock.patch("mikazuki.anima_fast_backend.environment._run_streaming", side_effect=fake_run), \
                mock.patch(
                    "mikazuki.anima_fast_backend.environment.audit_environment",
                    return_value=AuditResult(ok=False, errors=["anima: iopath expected 0.1.10, got None"]),
                ):
                install_environment(plan, lambda _line: None, progress=progress_events.append)

        self.assertEqual(progress_events[-1]["phase"], "broken")
        self.assertLess(progress_events[-1]["percent"], 100)

    def test_install_environment_preserves_task_id_in_install_state(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            source = self._make_source(project)
            self._make_constraints(project)
            layout = ExtensionLayout(project / "extensions" / "anima_lora")
            plan = build_environment_install_plan(project, layout, source, dry_run=False)
            write_install_state(layout, STATE_INSTALLING, {"task_id": "anima-install-keep-id", "plan": plan.as_dict()})

            discovered_python = _fake_discovered_python(plan)

            def fake_run(command, cwd, log, env=None, retries=0):
                if len(command) >= 3 and command[0] == str(discovered_python) and command[1:3] == ["-m", "venv"]:
                    plan.venv_python.parent.mkdir(parents=True)
                    plan.venv_python.write_text("", encoding="utf-8")
                if len(command) >= 3 and command[1:3] == ["python", "install"]:
                    discovered_python.parent.mkdir(parents=True)
                    discovered_python.write_text("", encoding="utf-8")
                log("[fake] command completed")

            def fake_copy(_plan):
                self._make_runtime_source(layout)

            with mock.patch("mikazuki.anima_fast_backend.environment._uv_command", return_value="uv"), \
                mock.patch("mikazuki.anima_fast_backend.environment.copy_source_snapshot", side_effect=fake_copy), \
                mock.patch("mikazuki.anima_fast_backend.environment._run_streaming", side_effect=fake_run), \
                mock.patch(
                    "mikazuki.anima_fast_backend.environment.audit_environment",
                    return_value=AuditResult(ok=True, facts={"anima": {"torch": "2.11.0+cu130"}}),
                ):
                install_environment(plan, lambda _line: None, task_id="anima-install-keep-id")

            payload = json.loads(layout.install_state.read_text(encoding="utf-8"))

        self.assertEqual(payload["facts"]["task_id"], "anima-install-keep-id")
        self.assertEqual(payload["state"], STATE_READY)

    def test_stale_installing_without_task_marks_broken(self):
        with tempfile.TemporaryDirectory() as td:
            layout = ExtensionLayout(Path(td) / "extensions" / "anima_lora")
            self._make_runtime_source(layout)
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
            self._make_runtime_source(layout)
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

            def fake_install(plan, log, task_id=None, progress=None):
                captured["source_root"] = plan.source_root
                from mikazuki.anima_fast_backend.extension_state import write_install_state

                write_install_state(layout, STATE_READY, {"audit": {"ok": True}})
                return AuditResult(ok=True)

            def fake_ensure(project_root, preferred, commit, log=None, github_url_prefix=None):
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

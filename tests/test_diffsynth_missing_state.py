"""#459: missing install_state.json must not look like a fresh install."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mikazuki.engines.diffsynth.extension_state import (
    FINGERPRINT_SCHEME,
    read_status,
    recover_missing_state,
)
from mikazuki.engines.diffsynth.settings import (
    PROJECT_ROOT_ENV,
    TRAIN_SCRIPT,
    Runtime,
    default_project_root,
    runtime as resolve_runtime,
)


def make_runtime(project_root: Path) -> Runtime:
    runtime = Runtime(project_root)
    (runtime.source / "diffsynth" / "models").mkdir(parents=True, exist_ok=True)
    (runtime.source / TRAIN_SCRIPT).parent.mkdir(parents=True, exist_ok=True)
    (runtime.source / TRAIN_SCRIPT).write_text("print('train')\n", encoding="utf-8")
    (runtime.source / "pyproject.toml").write_text("[project]\nname = 'diffsynth'\n", encoding="utf-8")
    (runtime.source / "diffsynth" / "models" / "model.py").write_text("x = 1\n", encoding="utf-8")
    runtime.python.parent.mkdir(parents=True, exist_ok=True)
    runtime.python.write_text("#!/python\n", encoding="utf-8")
    metadata = runtime.root / ".venv" / "lib" / "torch-2.8.0.dist-info"
    metadata.mkdir(parents=True, exist_ok=True)
    (metadata / "METADATA").write_text("Name: torch\nVersion: 2.8.0\n", encoding="utf-8")
    return runtime


class MissingStateRecoveryTests(unittest.TestCase):
    def test_absent_extension_is_not_installed(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = Runtime(Path(td))
            status = read_status(runtime, audit_fn=lambda _rt: self.fail("audit should not run"))
            self.assertEqual(status["state"], "not_installed")
            self.assertFalse(runtime.state_file.exists())

    def test_empty_extension_dir_is_not_installed(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = Runtime(Path(td))
            runtime.root.mkdir(parents=True)
            status = read_status(runtime, audit_fn=lambda _rt: self.fail("audit should not run"))
            self.assertEqual(status["state"], "not_installed")

    def test_partial_runtime_is_broken_not_not_installed(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = Runtime(Path(td))
            runtime.source.mkdir(parents=True)
            (runtime.root / ".venv").mkdir(parents=True)
            status = read_status(runtime, audit_fn=lambda _rt: self.fail("audit should not run"))
            self.assertEqual(status["state"], "broken")
            self.assertIn("不完整", status["reason"])
            self.assertFalse(runtime.state_file.exists())

    def test_complete_runtime_missing_state_recovers_to_ready(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            audit_calls = []

            def audit(rt):
                audit_calls.append(rt)
                return {"ok": True, "errors": [], "torch": "2.8.0", "cuda": "12.8", "gpu": True}

            status = read_status(runtime, audit_fn=audit)
            persisted = json.loads(runtime.state_file.read_text(encoding="utf-8"))
            second = read_status(runtime, audit_fn=lambda _rt: self.fail("second poll must not audit"))

        self.assertEqual(status["state"], "ready")
        self.assertEqual(len(audit_calls), 1)
        self.assertEqual(persisted["state"], "ready")
        self.assertEqual(persisted["facts"]["fingerprint_scheme"], FINGERPRINT_SCHEME)
        self.assertEqual(persisted["facts"]["recovery"], "missing_install_state")
        self.assertEqual(second["state"], "ready")

    def test_complete_runtime_audit_failure_persists_broken(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            status = read_status(
                runtime,
                audit_fn=lambda _rt: {"ok": False, "errors": ["未检测到 CUDA GPU，不能启动训练。"]},
            )
            persisted = json.loads(runtime.state_file.read_text(encoding="utf-8"))

        self.assertEqual(status["state"], "broken")
        self.assertIn("CUDA", status["reason"])
        self.assertEqual(persisted["state"], "broken")

    def test_recover_helper_matches_read_status(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = make_runtime(Path(td))
            recovered = recover_missing_state(
                runtime,
                audit_fn=lambda _rt: {"ok": True, "errors": [], "torch": "2.8.0", "cuda": "12.8", "gpu": True},
            )
        self.assertEqual(recovered["state"], "ready")


class ProjectRootResolutionTests(unittest.TestCase):
    def test_default_project_root_follows_package_not_cwd(self):
        package_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop(PROJECT_ROOT_ENV, None)
                previous = Path.cwd()
                try:
                    os.chdir(td)
                    self.assertEqual(default_project_root(), package_root)
                    self.assertEqual(resolve_runtime().project_root, package_root)
                finally:
                    os.chdir(previous)

    def test_env_override_wins(self):
        with tempfile.TemporaryDirectory() as td:
            override = Path(td).resolve()
            with mock.patch.dict(os.environ, {PROJECT_ROOT_ENV: str(override)}):
                self.assertEqual(default_project_root(), override)
                self.assertEqual(resolve_runtime().root, override / "extensions" / "diffsynth")


if __name__ == "__main__":
    unittest.main()

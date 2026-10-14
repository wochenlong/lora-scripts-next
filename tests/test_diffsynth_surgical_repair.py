"""#462: DiffSynth diagnose + surgical repair planning (no full wipe by default)."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mikazuki.engines.diffsynth.diagnose import actions_for_diagnosis, diagnose
from mikazuki.engines.diffsynth.installer import build_repair_plan, start_surgical_repair
from mikazuki.engines.diffsynth.settings import TRAIN_SCRIPT, Runtime
from mikazuki.download_sources import DownloadSources


def _touch_runtime(project_root: Path, *, with_python_dir=True, with_venv=True, with_source=True) -> Runtime:
    runtime = Runtime(project_root)
    if with_python_dir:
        runtime.python_install_dir.mkdir(parents=True, exist_ok=True)
        (runtime.python_install_dir / "marker").write_text("py", encoding="utf-8")
    if with_venv:
        runtime.python.parent.mkdir(parents=True, exist_ok=True)
        runtime.python.write_text("#!/python\n", encoding="utf-8")
    if with_source:
        (runtime.source / TRAIN_SCRIPT).parent.mkdir(parents=True, exist_ok=True)
        (runtime.source / TRAIN_SCRIPT).write_text("print('train')\n", encoding="utf-8")
        (runtime.source / "pyproject.toml").write_text("[project]\nname='diffsynth'\n", encoding="utf-8")
        (runtime.source / ".git").mkdir(parents=True, exist_ok=True)
    return runtime


def _ok_run(cmd, **kwargs):
    text = " ".join(str(c) for c in cmd)
    if "rev-parse" in text:
        from mikazuki.engines.diffsynth.manifest import UPSTREAM

        return subprocess.CompletedProcess(cmd, 0, UPSTREAM["commit"] + "\n", "")
    if "--help" in text:
        return subprocess.CompletedProcess(cmd, 0, "usage\n", "")
    if "import json, torch" in text or "import sys" in text:
        if "import json, torch" in text:
            return subprocess.CompletedProcess(
                cmd, 0, json.dumps({"torch": "2.8.0", "cuda": "12.8", "gpu": True}) + "\n", ""
            )
        return subprocess.CompletedProcess(cmd, 0, "python\n", "")
    return subprocess.CompletedProcess(cmd, 0, "", "")


class DiagnoseTests(unittest.TestCase):
    def test_empty_is_missing_all(self):
        with tempfile.TemporaryDirectory() as td:
            d = diagnose(Runtime(Path(td)), run=_ok_run)
        self.assertEqual(d["code"], "missing_all")
        self.assertEqual(d["recommended_actions"], ["fresh_install"])

    def test_partial_source_only_is_python_missing(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = _touch_runtime(Path(td), with_python_dir=False, with_venv=False, with_source=True)
            d = diagnose(runtime, run=_ok_run)
        self.assertEqual(d["code"], "python_runtime_missing")
        self.assertIn("repair_python_runtime", d["recommended_actions"])

    def test_missing_venv_recommends_repair_venv(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = _touch_runtime(Path(td), with_venv=False)
            d = diagnose(runtime, run=_ok_run)
        self.assertEqual(d["code"], "venv_missing")
        self.assertEqual(d["recommended_actions"][0], "repair_venv")

    def test_host_no_gpu_forbids_reinstall(self):
        def run(cmd, **kwargs):
            text = " ".join(str(c) for c in cmd)
            if "import json, torch" in text:
                return subprocess.CompletedProcess(
                    cmd, 0, json.dumps({"torch": "2.8.0", "cuda": None, "gpu": False}) + "\n", ""
                )
            return _ok_run(cmd, **kwargs)

        with tempfile.TemporaryDirectory() as td:
            runtime = _touch_runtime(Path(td))
            d = diagnose(runtime, run=run)
        self.assertEqual(d["code"], "host_no_gpu")
        self.assertEqual(d["recommended_actions"], [])
        self.assertFalse(d["allows_full_reinstall"])


class RepairPlanTests(unittest.TestCase):
    def test_repair_source_does_not_delete_venv_or_python(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = _touch_runtime(Path(td))
            plan = build_repair_plan(runtime, DownloadSources(), ["repair_source", "refresh_state"])
        self.assertEqual(plan["delete"], [])
        self.assertTrue(any(step["action"] == "repair_source" for step in plan["steps"]))
        for step in plan["steps"]:
            self.assertNotIn(str(runtime.root / ".venv"), step.get("delete") or [])
            self.assertNotIn(str(runtime.python_install_dir), step.get("delete") or [])

    def test_repair_venv_only_deletes_venv(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = _touch_runtime(Path(td))
            plan = build_repair_plan(runtime, DownloadSources(), ["repair_venv", "refresh_state"])
        self.assertEqual(plan["delete"], [str(runtime.root / ".venv")])
        self.assertNotIn(str(runtime.source), plan["delete"])
        self.assertNotIn(str(runtime.python_install_dir), plan["delete"])

    def test_full_reinstall_deletes_all_three(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = _touch_runtime(Path(td))
            plan = build_repair_plan(runtime, DownloadSources(), ["full_reinstall"])
        self.assertCountEqual(
            plan["delete"],
            [str(runtime.source), str(runtime.root / ".venv"), str(runtime.python_install_dir)],
        )

    def test_auto_actions_prefer_surgical(self):
        diagnosis = {
            "code": "source_incomplete",
            "recommended_actions": ["repair_source", "refresh_state"],
        }
        self.assertEqual(actions_for_diagnosis(diagnosis), ["repair_source", "refresh_state"])
        self.assertEqual(actions_for_diagnosis(diagnosis, explicit="full_reinstall"), ["full_reinstall"])

    def test_surgical_rejects_host_no_gpu(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = _touch_runtime(Path(td))
            with mock.patch(
                "mikazuki.engines.diffsynth.installer.diagnose",
                return_value={
                    "code": "host_no_gpu",
                    "summary": "no gpu",
                    "recommended_actions": [],
                    "allows_full_reinstall": False,
                },
            ):
                with self.assertRaisesRegex(ValueError, "CUDA GPU"):
                    start_surgical_repair(runtime, DownloadSources())

    def test_dry_run_returns_plan_without_spawning(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = _touch_runtime(Path(td))
            with mock.patch(
                "mikazuki.engines.diffsynth.installer.diagnose",
                return_value={
                    "code": "venv_missing",
                    "summary": "venv missing",
                    "recommended_actions": ["repair_venv", "refresh_state"],
                    "allows_full_reinstall": True,
                },
            ):
                result = start_surgical_repair(runtime, DownloadSources(), dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["plan"]["actions"][0], "repair_venv")
        self.assertNotIn("task_id", result)


if __name__ == "__main__":
    unittest.main()

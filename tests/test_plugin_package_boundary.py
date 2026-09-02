from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COPY_SCRIPT = ROOT / "build-scripts" / "03-copy-project.ps1"


def _powershell() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def _read_copy_policy() -> dict:
    executable = _powershell()
    if executable is None:
        raise unittest.SkipTest("PowerShell is required to inspect the Windows portable copy policy")

    # An empty project root proves policy inspection is side-effect free: it
    # must not build the frontend, initialize submodules, or copy files.
    with tempfile.TemporaryDirectory() as temp_dir:
        result = subprocess.run(
            [
                executable,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(COPY_SCRIPT),
                "-ProjectRoot",
                temp_dir,
                "-DescribeCopyPolicy",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    if result.returncode != 0:
        raise AssertionError(f"copy policy command failed: {result.stderr or result.stdout}")
    return json.loads(result.stdout)


def _requirement_names(path: Path) -> set[str]:
    names: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"([A-Za-z0-9_.-]+)", line)
        if match:
            names.add(match.group(1).lower().replace("_", "-"))
    return names


class PluginPackageBoundaryTests(unittest.TestCase):
    def test_core_portable_policy_excludes_plugin_source_and_runtime(self):
        policy = _read_copy_policy()

        self.assertEqual(policy["schemaVersion"], 1)
        excluded = {str(item).lower() for item in policy["excludedDirectories"]}
        self.assertIn("plugin-packages", excluded)
        self.assertIn("extensions", excluded)

    def test_core_frontend_has_no_pi_or_react_plugin_dependencies(self):
        manifest = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
        dependencies: set[str] = set()
        for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            dependencies.update(str(name).lower() for name in manifest.get(section, {}))

        forbidden_exact = {"react", "react-dom", "next", "@earendil-works/pi-coding-agent"}
        self.assertTrue(forbidden_exact.isdisjoint(dependencies), sorted(forbidden_exact & dependencies))
        self.assertFalse(any(name.startswith("@earendil-works/pi-") for name in dependencies))

    def test_core_python_requirements_have_no_plugin_runtime_dependencies(self):
        requirements = _requirement_names(ROOT / "requirements.txt")

        forbidden = {"react", "react-dom", "next", "pi-agent", "pi-coding-agent", "bun", "nodejs"}
        self.assertTrue(forbidden.isdisjoint(requirements), sorted(forbidden & requirements))


if __name__ == "__main__":
    unittest.main()

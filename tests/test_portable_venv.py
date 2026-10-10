from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from mikazuki.engines.portable_venv import (
    REPAIR_BROKEN,
    REPAIR_OK,
    REPAIR_RELOCATED,
    find_packaged_base_python,
    read_venv_home,
    relocate_venv_home,
    repair_venv_base,
    venv_base_missing,
)


def make_venv(root: Path, home: Path | None = None) -> Path:
    if sys.platform == "win32":
        python = root / ".venv" / "Scripts" / "python.exe"
    else:
        python = root / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    lines = [
        f"home = {home}" if home else "home = ",
        "include-system-site-packages = false",
        "version = 3.12.1",
        f"executable = {home / 'python.exe'}" if home else "executable = ",
        f"command = {home / 'python.exe'} -m venv {root / '.venv'}" if home else "command = ",
    ]
    (root / ".venv" / "pyvenv.cfg").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return python


def make_packaged_python(root: Path, version: str = "3.12") -> Path:
    if sys.platform == "win32":
        python = root / ".python" / f"cpython-{version}.11-windows-x86_64-none" / "python.exe"
    else:
        python = root / ".python" / f"cpython-{version}.11-linux-x86_64-gnu" / "bin" / "python3"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    return python


class ReadVenvHomeTests(unittest.TestCase):
    def test_reads_home(self):
        with tempfile.TemporaryDirectory() as td:
            python = make_venv(Path(td), Path("E:/build-machine/.python/cpython-3.12"))
            self.assertEqual(read_venv_home(python), Path("E:/build-machine/.python/cpython-3.12"))

    def test_missing_cfg_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            python = Path(td) / ".venv" / "bin" / "python"
            self.assertIsNone(read_venv_home(python))


class VenvBaseMissingTests(unittest.TestCase):
    def test_missing_home_is_broken(self):
        with tempfile.TemporaryDirectory() as td:
            python = make_venv(Path(td), Path(td) / "gone")
            self.assertTrue(venv_base_missing(python))

    def test_resolving_home_is_fine(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "base"
            home.mkdir()
            python = make_venv(Path(td), home)
            self.assertFalse(venv_base_missing(python))

    def test_missing_venv_is_not_a_repair_case(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertFalse(venv_base_missing(Path(td) / ".venv" / "bin" / "python"))


class FindPackagedBasePythonTests(unittest.TestCase):
    def test_finds_matching_version(self):
        with tempfile.TemporaryDirectory() as td:
            expected = make_packaged_python(Path(td), "3.12")
            found = find_packaged_base_python(Path(td) / ".python", "3.12")
            self.assertEqual(found, expected.resolve())

    def test_ignores_other_versions(self):
        with tempfile.TemporaryDirectory() as td:
            make_packaged_python(Path(td), "3.11")
            self.assertIsNone(find_packaged_base_python(Path(td) / ".python", "3.12"))

    def test_missing_dir_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(find_packaged_base_python(Path(td) / ".python", "3.12"))


class RelocateVenvHomeTests(unittest.TestCase):
    def test_rewrites_home_executable_and_drops_command(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            python = make_venv(root, root / "stale-home")
            base = make_packaged_python(root)
            relocate_venv_home(python, base)
            text = (root / ".venv" / "pyvenv.cfg").read_text(encoding="utf-8")
            self.assertIn(f"home = {base.parent}", text)
            self.assertIn(f"executable = {base}", text)
            self.assertIn("include-system-site-packages = false", text)
            self.assertIn("version = 3.12.1", text)
            self.assertNotIn("command", text)
            self.assertNotIn("stale-home", text)

    def test_adds_home_when_absent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            python = make_venv(root, None)
            base = make_packaged_python(root)
            relocate_venv_home(python, base)
            self.assertEqual(read_venv_home(python), base.parent)


class RepairVenvBaseTests(unittest.TestCase):
    def test_relocates_stale_home_to_packaged_python(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            python = make_venv(root, root / "stale-home")
            base = make_packaged_python(root)
            logs: list[str] = []
            result = repair_venv_base(python, root / ".python", "3.12", log=logs.append)
            self.assertEqual(result, REPAIR_RELOCATED)
            self.assertEqual(read_venv_home(python), base.parent)
            self.assertTrue(logs)

    def test_noop_when_home_resolves(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / "base"
            home.mkdir()
            python = make_venv(root, home)
            make_packaged_python(root)
            before = (root / ".venv" / "pyvenv.cfg").read_bytes()
            self.assertEqual(repair_venv_base(python, root / ".python", "3.12"), REPAIR_OK)
            self.assertEqual((root / ".venv" / "pyvenv.cfg").read_bytes(), before)

    def test_broken_when_no_packaged_python(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            python = make_venv(root, root / "stale-home")
            self.assertEqual(repair_venv_base(python, root / ".python", "3.12"), REPAIR_BROKEN)
            self.assertEqual(read_venv_home(python), root / "stale-home")

    def test_missing_venv_is_ok(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = repair_venv_base(root / ".venv" / "bin" / "python", root / ".python", "3.12")
            self.assertEqual(result, REPAIR_OK)


if __name__ == "__main__":
    unittest.main()

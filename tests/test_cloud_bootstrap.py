"""scripts/cloud/bootstrap.py 的纯逻辑单测：版本区间、宿主匹配、解释器选择、flag 指纹。"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_bootstrap():
    spec = importlib.util.spec_from_file_location("cloud_bootstrap", REPO_ROOT / "scripts" / "cloud" / "bootstrap.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bootstrap = _load_bootstrap()


class VersionSpecTests(unittest.TestCase):
    def test_version_key_strips_local_segment(self):
        self.assertEqual(bootstrap.version_key("2.8.0+cu128"), (2, 8, 0))
        self.assertEqual(bootstrap.version_key("12.4"), (12, 4))

    def test_spec_satisfied(self):
        self.assertTrue(bootstrap.spec_satisfied("2.8.0+cu128", ">=2.5.1"))
        self.assertTrue(bootstrap.spec_satisfied("3.12.3", ">=3.10,<3.13"))
        self.assertTrue(bootstrap.spec_satisfied("3.10.20", ">=3.10,<3.13"))
        self.assertFalse(bootstrap.spec_satisfied("3.13.0", ">=3.10,<3.13"))
        self.assertFalse(bootstrap.spec_satisfied("2.4.0", ">=2.5.1"))
        self.assertTrue(bootstrap.spec_satisfied("12.8", ">=12.4"))
        self.assertFalse(bootstrap.spec_satisfied("12.1", ">=12.4"))
        self.assertTrue(bootstrap.spec_satisfied("1.0.0", ""))
        self.assertTrue(bootstrap.spec_satisfied("2.8.0", "==2.8.0"))
        self.assertFalse(bootstrap.spec_satisfied("2.8.1", "==2.8.0"))
        self.assertTrue(bootstrap.spec_satisfied("2.8.1", "!=2.8.0"))

    def test_invalid_spec_raises(self):
        with self.assertRaises(ValueError):
            bootstrap.spec_satisfied("1.0", "~=1.0")


class HostSatisfiesTests(unittest.TestCase):
    REQUIRES = {"python": ">=3.10,<3.13", "torch": ">=2.5.1", "cuda": ">=12.4"}

    def test_full_match(self):
        facts = {"python": "3.12.3", "torch": "2.8.0+cu128", "cuda": "12.8"}
        self.assertTrue(bootstrap.host_satisfies(facts, self.REQUIRES))

    def test_missing_torch_never_matches_torch_requirement(self):
        facts = {"python": "3.12.3", "torch": None, "cuda": None}
        self.assertFalse(bootstrap.host_satisfies(facts, self.REQUIRES))

    def test_torch_present_but_old_cuda(self):
        facts = {"python": "3.12.3", "torch": "2.5.1+cu121", "cuda": "12.1"}
        self.assertFalse(bootstrap.host_satisfies(facts, self.REQUIRES))

    def test_empty_requires_matches_anything(self):
        self.assertTrue(bootstrap.host_satisfies({"python": "3.12.3"}, {}))


class PickInterpreterTests(unittest.TestCase):
    def test_prefers_torch_with_gpu(self):
        plain = {"python": "3.12.3", "torch": None, "cuda": None, "gpu": False, "python_path": "/usr/bin/python3"}
        torch_cpu = {"python": "3.12.3", "torch": "2.9.0", "cuda": None, "gpu": False, "python_path": "/a/bin/python"}
        torch_gpu = {"python": "3.10.20", "torch": "2.8.0+cu128", "cuda": "12.8", "gpu": True, "python_path": "/b/bin/python"}
        self.assertEqual(bootstrap.pick_best_interpreter([plain, torch_cpu, torch_gpu]), torch_gpu)

    def test_skips_python_outside_gui_range(self):
        old = {"python": "3.9.0", "torch": "2.8.0", "cuda": "12.8", "gpu": True, "python_path": "/a"}
        ok = {"python": "3.12.3", "torch": None, "cuda": None, "gpu": False, "python_path": "/b"}
        self.assertEqual(bootstrap.pick_best_interpreter([old, ok]), ok)
        self.assertIsNone(bootstrap.pick_best_interpreter([old]))


class ManifestLoadingTests(unittest.TestCase):
    def test_real_repo_manifests(self):
        packs = {p["engine_id"]: p for p in bootstrap.load_pack_manifests(REPO_ROOT / "mikazuki" / "engines")}
        self.assertNotIn("your-engine", packs)  # _template 跳过
        self.assertTrue(packs["musubi"]["slim_supported"])
        for engine_id in ("kohya", "anima-fast", "ai-toolkit", "diffsynth"):
            self.assertFalse(packs[engine_id]["slim_supported"], engine_id)

    def test_compatible_engines(self):
        packs = bootstrap.load_pack_manifests(REPO_ROOT / "mikazuki" / "engines")
        good = {"python": "3.12.3", "torch": "2.8.0+cu128", "cuda": "12.8", "arch": "x86_64"}
        matched = bootstrap.compatible_engines(good, packs)
        self.assertEqual([p["engine_id"] for p in matched], ["musubi"])
        no_torch = {"python": "3.12.3", "torch": None, "cuda": None}
        self.assertEqual(bootstrap.compatible_engines(no_torch, packs), [])


class FlagTests(unittest.TestCase):
    def test_write_read_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            facts = {"python_path": "/x/bin/python", "python": "3.12.3", "torch": "2.8.0+cu128", "cuda": "12.8", "arch": "x86_64"}
            bootstrap.write_flag(root, "musubi", facts)
            flag = bootstrap.read_flag(root)
            self.assertEqual(flag["engine"], "musubi")
            self.assertEqual(flag["python_version"], "3.12.3")
            self.assertEqual(flag["torch_version"], "2.8.0+cu128")

    def test_read_missing_and_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.assertIsNone(bootstrap.read_flag(root))
            (root / ".cloud_install_done").write_text("{broken", encoding="utf-8")
            self.assertIsNone(bootstrap.read_flag(root))

    def test_mismatch_detection(self):
        flag = {"python_path": "/x/bin/python", "python_version": "3.12.3", "torch_version": "2.8.0+cu128", "arch": "x86_64"}
        same = {"python": "3.12.3", "torch": "2.8.0+cu128", "arch": "x86_64"}
        self.assertEqual(bootstrap.flag_mismatch(flag, same), [])
        changed_torch = {"python": "3.12.3", "torch": "2.9.0+cu130", "arch": "x86_64"}
        diffs = bootstrap.flag_mismatch(flag, changed_torch)
        self.assertEqual(len(diffs), 1)
        self.assertIn("torch", diffs[0])
        changed_arch = {"python": "3.12.3", "torch": "2.8.0+cu128", "arch": "aarch64"}
        self.assertEqual(len(bootstrap.flag_mismatch(flag, changed_arch)), 1)
        self.assertTrue(bootstrap.flag_mismatch(flag, None))


if __name__ == "__main__":
    unittest.main()

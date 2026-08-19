import json
import tempfile
import unittest
from pathlib import Path

from mikazuki.products.registry import Registry, product_id_for_path


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "registry.jsonl"

    def tearDown(self):
        self._tmp.cleanup()

    def test_run_round_trip(self):
        reg = Registry(self.path)
        reg.record_run(task_id="t1", train_type="sdxl-lora", config_path="config/autosave/x.toml",
                       output_dir="./output", output_name="my-lora")
        reg2 = Registry(self.path)
        runs = reg2.list_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["task_id"], "t1")
        self.assertEqual(runs[0]["train_type"], "sdxl-lora")
        self.assertTrue(Path(runs[0]["output_dir"]).is_absolute())

    def test_corrupted_lines_are_skipped(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            '{"op": "run", "task_id": "ok", "registered_at": 1}\n'
            'not json at all\n'
            '{"op": "scan_dir", "path": "/tmp/x"}\n',
            encoding="utf-8",
        )
        reg = Registry(self.path)
        self.assertIn("ok", reg.runs)
        self.assertEqual(reg.scan_dirs, ["/tmp/x"])

    def test_product_state_merges(self):
        reg = Registry(self.path)
        pid = product_id_for_path("/tmp/a.safetensors")
        reg.update_product_state(pid, path="/tmp/a.safetensors")
        reg.update_product_state(pid, derived_from="other-id")
        reg2 = Registry(self.path)
        state = reg2.get_product_state(pid)
        self.assertEqual(state["path"], "/tmp/a.safetensors")
        self.assertEqual(state["derived_from"], "other-id")

    def test_scan_dir_dedup(self):
        reg = Registry(self.path)
        reg.add_scan_dir("/tmp/dup")
        reg.add_scan_dir("/tmp/dup")
        self.assertEqual(reg.scan_dirs, [str(Path("/tmp/dup").resolve())])

    def test_compaction(self):
        reg = Registry(self.path)
        reg._op_count = 1001
        reg.add_scan_dir("/tmp/compact")
        reg2 = Registry(self.path)
        self.assertIn(str(Path("/tmp/compact").resolve()), reg2.scan_dirs)
        lines = self.path.read_text(encoding="utf-8").strip().splitlines()
        self.assertLessEqual(len(lines), 10)


class ProductIdTests(unittest.TestCase):
    def test_stable_for_same_path(self):
        self.assertEqual(product_id_for_path("/tmp/x.safetensors"),
                         product_id_for_path("/tmp/x.safetensors"))

    def test_distinct_for_distinct_paths(self):
        self.assertNotEqual(product_id_for_path("/tmp/a.safetensors"),
                            product_id_for_path("/tmp/b.safetensors"))


if __name__ == "__main__":
    unittest.main()

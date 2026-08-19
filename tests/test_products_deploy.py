import tempfile
import unittest
from pathlib import Path

from mikazuki.products import deploy as deploy_mod
from mikazuki.products.registry import Registry


class DeployTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.registry = Registry(self.root / "registry.jsonl")
        self.targets_path = self.root / "targets.json"
        self.source = self.root / "out" / "my-lora.safetensors"
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b"weights" * 1000)
        self.target_dir = self.root / "inference" / "loras"
        self.target_dir.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _deploy(self, method="copy"):
        return deploy_mod.deploy_product(
            self.registry,
            product_path=str(self.source),
            product_family="sdxl",
            target_name="webui",
            target_dir=str(self.target_dir),
            method=method,
        )

    def test_targets_round_trip(self):
        deploy_mod.save_targets({"webui": str(self.target_dir)}, self.targets_path)
        self.assertEqual(deploy_mod.load_targets(self.targets_path),
                         {"webui": str(self.target_dir.resolve())})
        self.assertEqual(deploy_mod.load_targets(self.root / "missing.json"), {})

    def test_deploy_copy_and_reconcile_ok(self):
        result = self._deploy()
        self.assertEqual(result["status"], "deployed")
        deployed = self.target_dir / self.source.name
        self.assertTrue(deployed.is_file())
        self.assertEqual(deployed.read_bytes(), self.source.read_bytes())
        results = deploy_mod.reconcile_all(self.registry, {"webui": str(self.target_dir)})
        self.assertEqual(results[0]["status"], "ok")

    def test_deploy_twice_is_idempotent(self):
        self._deploy()
        self.assertEqual(self._deploy()["status"], "already")

    def test_missing_target_is_restored(self):
        self._deploy()
        (self.target_dir / self.source.name).unlink()
        results = deploy_mod.reconcile_all(self.registry, {"webui": str(self.target_dir)})
        self.assertEqual(results[0]["status"], "restored")
        self.assertTrue((self.target_dir / self.source.name).is_file())

    def test_same_name_different_content_is_conflict_not_overwrite(self):
        intruder = self.target_dir / self.source.name
        intruder.write_bytes(b"someone-else")
        with self.assertRaises(FileExistsError):
            self._deploy()
        self.assertEqual(intruder.read_bytes(), b"someone-else")

    def test_undeploy_removes_copy(self):
        self._deploy()
        result = deploy_mod.undeploy_product(
            self.registry, product_path=str(self.source), target_name="webui",
        )
        self.assertEqual(result["status"], "removed")
        self.assertFalse((self.target_dir / self.source.name).exists())

    def test_undeploy_conflict_keeps_foreign_file(self):
        self._deploy()
        deployed = self.target_dir / self.source.name
        deployed.write_bytes(b"tampered")
        result = deploy_mod.undeploy_product(
            self.registry, product_path=str(self.source), target_name="webui",
        )
        self.assertEqual(result["status"], "conflict")
        self.assertTrue(deployed.is_file())

    def test_check_entry_is_read_only(self):
        self._deploy()
        deployed = self.target_dir / self.source.name
        entry = self.registry.get_product_state(
            deploy_mod.product_id_for_path(self.source))["deployed_to"]["webui"]
        self.assertEqual(deploy_mod.check_entry(entry)["status"], "ok")
        self.assertTrue(deployed.is_file())

    def test_clear_product_state(self):
        self._deploy()
        pid = deploy_mod.product_id_for_path(self.source)
        self.registry.clear_product_state(pid)
        self.assertEqual(self.registry.get_product_state(pid), {})
        reg2 = Registry(self.root / "registry.jsonl")
        self.assertEqual(reg2.get_product_state(pid), {})


if __name__ == "__main__":
    unittest.main()

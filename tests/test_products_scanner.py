import json
import tempfile
import unittest
from pathlib import Path

from mikazuki.products.registry import Registry
from mikazuki.products.scanner import (
    classify_family,
    collect_products,
    is_lycoris_like,
    resolve_output_path,
    scan_directory,
    split_epoch_stem,
    summarize_product,
)


def write_safetensors(path: Path, metadata: dict) -> None:
    """Minimal safetensors file: 8-byte header length + JSON header, no tensors."""
    header = json.dumps({"__metadata__": metadata}).encode("utf-8")
    path.write_bytes(len(header).to_bytes(8, "little") + header)


class HelpersTests(unittest.TestCase):
    def test_resolve_output_path_relative(self):
        resolved = resolve_output_path("./output", cwd=Path("/srv/app"))
        self.assertEqual(resolved, str(Path("/srv/app/output").resolve()))

    def test_resolve_output_path_absolute(self):
        resolved = resolve_output_path("/data/out", cwd=Path("/srv/app"))
        self.assertEqual(resolved, str(Path("/data/out").resolve()))

    def test_resolve_output_path_empty(self):
        self.assertIsNone(resolve_output_path(None))
        self.assertIsNone(resolve_output_path(""))

    def test_split_epoch_stem(self):
        self.assertEqual(split_epoch_stem("my-lora-000003"), ("my-lora", 3, None))
        self.assertEqual(split_epoch_stem("my-lora"), ("my-lora", None, None))
        self.assertEqual(split_epoch_stem("my-lora-step000100"), ("my-lora", None, 100))
        self.assertEqual(split_epoch_stem("my-lora-000002-step000100"), ("my-lora", 2, 100))

    def test_classify_family(self):
        self.assertEqual(classify_family({"ss_base_model_version": "sd_xl_base_1.0"}), "sdxl")
        self.assertEqual(classify_family({"ss_network_module": "networks.lora_flux"}), "flux")
        self.assertEqual(classify_family({"ss_base_model_version": "sd3.5_large"}), "sd3")
        self.assertEqual(classify_family({"ss_network_module": "networks.lora"}), "sd")
        self.assertEqual(classify_family({}), "other")

    def test_is_lycoris_like(self):
        self.assertTrue(is_lycoris_like({"ss_network_module": "lycoris.kohya"}))
        self.assertFalse(is_lycoris_like({"ss_network_module": "networks.lora"}))


class ScanTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_summarize_reads_header_only(self):
        target = self.dir / "lora-000001.safetensors"
        write_safetensors(target, {
            "ss_network_dim": "128",
            "ss_network_alpha": "64",
            "ss_base_model_version": "sd_xl_base_1.0",
        })
        summary = summarize_product(target)
        self.assertEqual(summary["dim"], 128)
        self.assertEqual(summary["alpha"], 64.0)
        self.assertEqual(summary["epoch"], 1)
        self.assertEqual(summary["group_key"], "lora")
        self.assertEqual(summary["family"], "sdxl")
        self.assertTrue(Path(summary["path"]).is_absolute())

    def test_scan_directory_skips_non_models(self):
        write_safetensors(self.dir / "a.safetensors", {})
        (self.dir / "note.txt").write_text("hi", encoding="utf-8")
        products = scan_directory(self.dir)
        self.assertEqual(len(products), 1)

    def test_collect_products_groups_epochs_and_marks_missing(self):
        write_safetensors(self.dir / "run1-000001.safetensors", {"ss_network_dim": "32"})
        write_safetensors(self.dir / "run1-000002.safetensors", {"ss_network_dim": "32"})
        write_safetensors(self.dir / "run1.safetensors", {"ss_network_dim": "32"})

        reg = Registry(self.dir / "registry.jsonl")
        # A product whose file was deleted afterwards: must surface as missing.
        ghost = self.dir / "ghost.safetensors"
        from mikazuki.products.registry import product_id_for_path
        reg.update_product_state(product_id_for_path(ghost), path=str(ghost.resolve()))

        listing = collect_products(reg, extra_dirs=[str(self.dir)])
        self.assertEqual(len(listing["groups"]), 2)
        run1 = next(g for g in listing["groups"] if g["name"] == "run1")
        self.assertEqual(len(run1["products"]), 3)
        epochs = [p["epoch"] for p in run1["products"]]
        self.assertEqual(epochs, [1, 2, None])
        ghost_group = next(g for g in listing["groups"] if g["name"] == "ghost")
        self.assertEqual(ghost_group["products"][0]["status"], "missing")

    def test_run_matching_by_output_dir_and_name(self):
        write_safetensors(self.dir / "mylora-000001.safetensors", {})
        reg = Registry(self.dir / "registry.jsonl")
        reg.record_run(task_id="task-9", train_type="sdxl-lora",
                       config_path="config/autosave/x.toml",
                       output_dir=str(self.dir), output_name="mylora")
        listing = collect_products(reg, extra_dirs=[str(self.dir)])
        product = listing["groups"][0]["products"][0]
        self.assertEqual(product["run_task_id"], "task-9")
        self.assertEqual(product["train_type"], "sdxl-lora")


if __name__ == "__main__":
    unittest.main()

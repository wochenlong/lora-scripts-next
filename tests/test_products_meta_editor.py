import json
import tempfile
import unittest
from pathlib import Path

from mikazuki.products import meta_editor
from mikazuki.products.meta_editor import MetadataEditError, read_metadata, write_metadata


def write_model(path: Path, metadata: dict, weights: bytes = b"\x00\x01\x02\x03" * 256) -> bytes:
    header = json.dumps({
        "__metadata__": metadata,
        "weight_a": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]},
    }).encode("utf-8")
    path.write_bytes(len(header).to_bytes(8, "little") + header + weights)
    return weights


class MetaEditorTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "lora.safetensors"

    def tearDown(self):
        self._tmp.cleanup()

    def test_round_trip_preserves_weight_bytes(self):
        weights = write_model(self.path, {"ss_network_dim": "32", "old_key": "old"})
        result = write_metadata(str(self.path), {"ss_network_dim": "32", "new_key": "new"})
        self.assertEqual(read_metadata(str(self.path)), {"ss_network_dim": "32", "new_key": "new"})
        # weight bytes identical
        data = self.path.read_bytes()
        header_len = int.from_bytes(data[:8], "little")
        self.assertEqual(data[8 + header_len:], weights)
        self.assertTrue(Path(result["backup"]).is_file())

    def test_removing_all_keys_drops_metadata_section(self):
        write_model(self.path, {"a": "1"})
        write_metadata(str(self.path), {})
        header_len = int.from_bytes(self.path.read_bytes()[:8], "little")
        header = json.loads(self.path.read_bytes()[8:8 + header_len])
        self.assertNotIn("__metadata__", header)
        self.assertIn("weight_a", header)

    def test_non_string_values_coerced(self):
        write_model(self.path, {})
        write_metadata(str(self.path), {"n": 3, "f": 1.5, "obj": {"a": 1}, "  ": "skip"})
        self.assertEqual(read_metadata(str(self.path)), {"n": "3", "f": "1.5", "obj": '{"a": 1}'})

    def test_rejects_non_safetensors(self):
        ckpt = Path(self._tmp.name) / "model.ckpt"
        ckpt.write_bytes(b"whatever")
        with self.assertRaises(MetadataEditError):
            write_metadata(str(ckpt), {"a": "1"})

    def test_backup_created_once(self):
        write_model(self.path, {"v": "1"})
        write_metadata(str(self.path), {"v": "2"})
        backup = Path(str(self.path) + ".bak")
        self.assertEqual(meta_editor.read_metadata(str(backup)), {"v": "1"})
        write_metadata(str(self.path), {"v": "3"})
        self.assertEqual(meta_editor.read_metadata(str(backup)), {"v": "1"})


if __name__ == "__main__":
    unittest.main()

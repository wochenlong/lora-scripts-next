import json
import tempfile
import unittest
from pathlib import Path

from mikazuki.products import actions
from mikazuki.products.actions import (
    ActionError,
    build_merge_args,
    build_resize_args,
    check_resizable,
)


def write_lora(path: Path, metadata: dict, tensor_keys=("lora_down",)) -> None:
    header = {"__metadata__": metadata}
    for i, key in enumerate(tensor_keys):
        header[f"model.{key}"] = {"dtype": "F32", "shape": [1], "data_offsets": [i, i + 1]}
    payload = json.dumps(header).encode("utf-8")
    path.write_bytes(len(payload).to_bytes(8, "little") + payload)


class ResizeArgsTests(unittest.TestCase):
    def test_fixed_rank(self):
        args = build_resize_args("in.safetensors", "out.safetensors", new_rank=32)
        self.assertEqual(args, ["--model", "in.safetensors", "--save_to", "out.safetensors",
                                "--new_rank", "32"])

    def test_dynamic(self):
        args = build_resize_args("in", "out", new_rank=16, dynamic_method="sv_ratio",
                                 dynamic_param=0.9, save_precision="fp16")
        self.assertIn("--dynamic_method", args)
        self.assertIn("0.9", args)
        self.assertIn("--save_precision", args)


class MergeArgsTests(unittest.TestCase):
    def test_concat(self):
        args = build_merge_args(["a", "b"], [1.0, 0.5], "out", concat=True)
        self.assertEqual(args[args.index("--models") + 1: args.index("--ratios")], ["a", "b"])
        self.assertIn("--concat", args)


class ResizableCheckTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_kohya_lora_ok(self):
        p = self.dir / "a.safetensors"
        write_lora(p, {"ss_network_module": "networks.lora"})
        check_resizable(str(p))

    def test_lycoris_rejected(self):
        p = self.dir / "lokr.safetensors"
        write_lora(p, {"ss_network_module": "lycoris.kohya"})
        with self.assertRaises(ActionError):
            check_resizable(str(p))

    def test_no_lora_keys_rejected(self):
        p = self.dir / "plain.safetensors"
        write_lora(p, {}, tensor_keys=("weight",))
        with self.assertRaises(ActionError):
            check_resizable(str(p))


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
import unittest


class AnimaDoraSchemaTests(unittest.TestCase):
    def test_dora_is_exposed_as_hidden_lycoris_adapter_type(self):
        schema = Path("mikazuki/schema/sd3-lora.ts").read_text(encoding="utf-8")

        self.assertIn('"dora"', schema)
        self.assertIn('lora_type: Schema.const("dora").required()', schema)
        self.assertIn('network_module: Schema.const("lycoris.kohya")', schema)
        self.assertIn('lycoris_algo: Schema.const("lora")', schema)
        self.assertIn("dora_wd: Schema.const(true)", schema)
        self.assertIn("DoRA dropout", schema)


if __name__ == "__main__":
    unittest.main()

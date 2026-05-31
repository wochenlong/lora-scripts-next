from __future__ import annotations

import ast
import unittest
from pathlib import Path


class AnimaFastStaticIntegrationTests(unittest.TestCase):
    def test_schema_file_exists_and_uses_fast_train_type(self):
        schema = Path("mikazuki/schema/anima-lora-fast.ts").read_text(encoding="utf-8")
        shared = Path("mikazuki/schema/shared.ts").read_text(encoding="utf-8")

        self.assertIn('default("anima-lora-fast")', schema)
        self.assertIn("ANIMA_FAST_LR_OPTIMIZER", schema)
        self.assertIn('"Automagic"', shared)
        self.assertNotIn("prodigyplus.ProdigyPlusScheduleFree", shared[shared.index("ANIMA_FAST_LR_OPTIMIZER"):])
        self.assertIn('Schema.const("lora")', schema)

    def test_fast_train_type_is_not_legacy_trainer_mapping(self):
        source = Path("mikazuki/app/api.py").read_text(encoding="utf-8")
        module = ast.parse(source)
        mapping = None
        for node in module.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "trainer_mapping":
                        mapping = ast.literal_eval(node.value)
        self.assertIsNotNone(mapping)
        self.assertNotIn("anima-lora-fast", mapping)
        self.assertEqual(mapping["anima-lora"], "./scripts/dev/anima_train_network.py")
        self.assertEqual(mapping["sd3-lora"], "./scripts/dev/anima_train_network.py")

    def test_api_contains_fast_early_branch_and_plugin_routes(self):
        source = Path("mikazuki/app/api.py").read_text(encoding="utf-8")

        self.assertIn("model_train_type == ANIMA_FAST_TRAIN_TYPE", source)
        self.assertIn('"/plugins/anima-lora/status"', source)
        self.assertIn('"/plugins/anima-lora/preflight"', source)
        self.assertIn('"/plugins/anima-lora/dry-run"', source)
        self.assertIn('"/plugins/anima-lora/install/log/stream/{task_id}"', source)
        self.assertLess(source.index("model_train_type == ANIMA_FAST_TRAIN_TYPE"), source.index("trainer_file = trainer_mapping[model_train_type]"))

    def test_frontend_dist_registers_anima_fast_entry(self):
        app = Path("frontend/dist/assets/app.547295de.js").read_text(encoding="utf-8")
        page = Path("frontend/dist/lora/anima-fast.html")
        data = Path("frontend/dist/assets/anima-fast.html.data.js")
        component = Path("frontend/dist/assets/anima-fast.html.page.js")

        self.assertTrue(page.is_file())
        self.assertTrue(data.is_file())
        self.assertTrue(component.is_file())
        self.assertIn("/lora/anima-fast.html", app)
        self.assertIn('"text":"Fast 模式","link":"/lora/anima-fast.md"', app)
        self.assertIn("anima-lora-fast", data.read_text(encoding="utf-8"))
        self.assertIn("data-anima-fast-install", component.read_text(encoding="utf-8"))
        self.assertIn("anima-fast-dataset-guide", page.read_text(encoding="utf-8"))
        self.assertIn("data-anima-fast-guide-toggle", page.read_text(encoding="utf-8"))
        self.assertIn("sorryhyun/anima_lora", page.read_text(encoding="utf-8"))
        self.assertIn("anima-fast-credit", page.read_text(encoding="utf-8"))
        self.assertIn("anima-fast-doc-links", page.read_text(encoding="utf-8"))
        self.assertIn("docs/anima-fast.md", page.read_text(encoding="utf-8"))

    def test_benchmark_example_configs_exist(self):
        examples = Path("docs/examples")
        for name in (
            "anima-lora-benchmark-kohya.toml",
            "anima-lora-benchmark-fast.toml",
            "anima-lora-benchmark-dataset.toml",
        ):
            self.assertTrue((examples / name).is_file(), name)

    def test_anima_fast_docs_mention_license_and_benchmark(self):
        text = Path("docs/anima-fast.md").read_text(encoding="utf-8")
        self.assertIn("MIT License", text)
        self.assertIn("7.1 s/step", text)
        self.assertIn("2.8 s/step", text)
        merge = Path("docs/anima-fast-merge-checklist.md").read_text(encoding="utf-8")
        self.assertIn("sorryhyun/anima_lora", merge)


if __name__ == "__main__":
    unittest.main()

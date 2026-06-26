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
        fast_optimizer = shared[shared.index("ANIMA_FAST_LR_OPTIMIZER"):]
        self.assertIn('"Automagic"', shared[: shared.index("ANIMA_FAST_LR_OPTIMIZER")])
        self.assertNotIn('"Automagic"', fast_optimizer)
        self.assertNotIn("prodigyplus.ProdigyPlusScheduleFree", fast_optimizer)
        self.assertNotIn('"EmoSens"', fast_optimizer)
        self.assertIn('"EmoSens"', shared[: shared.index("ANIMA_FAST_LR_OPTIMIZER")])
        self.assertIn('Schema.const("lora")', schema)

    def test_fast_adapter_does_not_whitelist_emosens(self):
        adapter = Path("mikazuki/anima_fast_backend/adapter.py").read_text(encoding="utf-8")
        self.assertIn("FAST_SUPPORTED_OPTIMIZERS", adapter)
        self.assertNotIn('"EmoSens"', adapter)
        self.assertNotIn('"Automagic",', adapter[adapter.index("FAST_SUPPORTED_OPTIMIZERS"): adapter.index("@dataclass")])

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
        installer = Path("frontend/dist/assets/anima-fast-install.js").read_text(encoding="utf-8")

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
        self.assertNotIn("标准模式（Kohya）见 /lora/sd3.html", component.read_text(encoding="utf-8"))
        self.assertNotIn("标准模式（Kohya）见 /lora/sd3.html", page.read_text(encoding="utf-8"))
        self.assertIn("data-anima-fast-ready", installer)
        self.assertIn("b.hidden = ready", installer)
        self.assertIn('b.style.display = ready ? "none" : ""', installer)
        self.assertIn('q("[data-anima-fast-status]").forEach', installer)
        self.assertIn("dedupeInstallPanels", installer)
        self.assertIn("setControls(last);", installer)
        self.assertIn("already_ready", installer)
        disabled_controls = installer[
            installer.index('q(".right-container button").forEach') : installer.index("document.body.classList.toggle", installer.index('q(".right-container button").forEach'))
        ]
        self.assertIn('t === "开始训练"', disabled_controls)
        self.assertIn('t === "Start training"', disabled_controls)
        self.assertNotIn('t === "✨加载训练预设✨"', disabled_controls)
        self.assertNotIn('t === "Load training preset"', disabled_controls)
        self.assertNotIn('t === "保存参数"', disabled_controls)
        self.assertNotIn('t === "Save parameters"', disabled_controls)
        self.assertNotIn('t === "导入配置文件"', disabled_controls)
        self.assertNotIn('t === "Import config"', disabled_controls)

    def test_fast_install_log_uses_compact_height(self):
        expected = "max-height:140px"
        files = (
            Path("scripts/patch-anima-fast-entry.py"),
            Path("frontend/dist/assets/anima-fast.html.page.js"),
            Path("frontend/dist/lora/anima-fast.html"),
        )

        for path in files:
            text = path.read_text(encoding="utf-8")
            self.assertIn("data-anima-fast-log", text, path)
            self.assertIn(expected, text, path)
            self.assertNotIn("max-height:260px", text, path)

    def test_fast_page_component_imports_versioned_app_module(self):
        component = Path("frontend/dist/assets/anima-fast.html.page.js").read_text(encoding="utf-8")
        self.assertIn('from"./app.547295de.js?v=20260626-configimport1"', component)
        self.assertNotIn('from"./app.547295de.js";', component)

    def test_fast_page_columns_use_content_height(self):
        css = Path("frontend/dist/assets/sd-trainer-ui-polish.css").read_text(encoding="utf-8")
        self.assertIn(
            "body.anima-fast-page .theme-container.no-navbar .example-container",
            css,
        )
        self.assertIn("align-items: flex-start", css)
        self.assertIn("height: auto", css)
        self.assertIn("min-height: 100vh", css)

    def test_frontend_dist_uses_project_version_cache_bust(self):
        version = Path("VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(version, "2.8.2")

        for path in Path("frontend/dist").rglob("*.html"):
            html = path.read_text(encoding="utf-8")
            if "sd-trainer-brand.js" in html:
                self.assertIn(f"sd-trainer-brand.js?v={version}", html, path)
            if "sd-nav-i18n.js" in html:
                self.assertIn(f"sd-nav-i18n.js?v={version}", html, path)

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

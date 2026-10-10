from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mikazuki.engines.musubi.adapter import AdapterError, adapt_config, dump_train_toml
from mikazuki.engines.musubi.families import (
    IDEOGRAM4,
    KREA2,
    cache_extra_args,
    family_for_train_type,
    family_for_variant,
)
from mikazuki.engines.musubi.launcher import (
    build_cache_latents_spec,
    build_cache_text_encoder_spec,
    build_train_spec,
)
from mikazuki.engines.musubi.manifest import CAPABILITIES, TRAIN_TYPES
from mikazuki.engines.musubi.preflight import ProbeFacts, run_preflight
from mikazuki.engines.musubi.settings import RuntimeConfig
from mikazuki.model_assets import check_assets, manifest_for, patch_ideogram4_source, tokenizer_dir_for
from mikazuki.utils.config_import import PAGE_SPECS, TRAIN_TYPE_TARGETS, analyze_train_type


def make_runtime(root: Path) -> RuntimeConfig:
    return RuntimeConfig(
        musubi_root=(root / "vendor" / "musubi-tuner").resolve(),
        python=(root / "vendor" / "musubi-tuner" / ".venv" / "Scripts" / "python.exe").resolve(),
        lora_next_root=root.resolve(),
        output_dir=(root / "output" / "musubi").resolve(),
        logging_dir=(root / "logs" / "musubi").resolve(),
        cache_dir=(root / ".cache" / "musubi").resolve(),
    )


def ideogram4_config(root: Path) -> dict:
    return {
        "model_train_type": "ideogram4-lora",
        "dit": "./sd-models/ideogram4/ideogram4_fp8_scaled.safetensors",
        "vae": "./sd-models/ideogram4/flux2-vae.safetensors",
        "text_encoder": "./sd-models/ideogram4/qwen3vl_8b_fp8_scaled.safetensors",
        "train_data_dir": str(root / "train"),
        "resolution": "1024,1024",
        "train_batch_size": 1,
        "learning_rate": "1e-4",
        "mixed_precision": "bf16",
        "max_train_epochs": 16,
    }


def write_runtime_files(runtime: RuntimeConfig) -> None:
    runtime.musubi_root.mkdir(parents=True, exist_ok=True)
    runtime.python.parent.mkdir(parents=True, exist_ok=True)
    runtime.python.write_text("", encoding="utf-8")
    for name in (
        IDEOGRAM4.cache_latents_script,
        IDEOGRAM4.cache_text_encoder_script,
        IDEOGRAM4.train_script,
        KREA2.cache_latents_script,
        KREA2.cache_text_encoder_script,
        KREA2.train_script,
    ):
        (runtime.musubi_root / name).write_text("", encoding="utf-8")


def probe_with(vram_mb: int = 24576) -> object:
    def probe(_runtime: RuntimeConfig) -> ProbeFacts:
        return ProbeFacts(
            python_version="3.12.0",
            torch_version="2.6.0",
            cuda_available=True,
            cuda_version="12.8",
            gpu_name="test-gpu",
            vram_total_mb=vram_mb,
            transformers_version="4.57.6",
        )

    return probe


class FamilyRegistryTests(unittest.TestCase):
    def test_manifest_registers_both_train_types(self):
        self.assertEqual(TRAIN_TYPES["krea2-lora"], "krea2")
        self.assertEqual(TRAIN_TYPES["ideogram4-lora"], "ideogram4")
        self.assertIn("ideogram4", CAPABILITIES["model_families"])
        self.assertIn("ideogram4", CAPABILITIES["variants"])

    def test_variant_and_train_type_resolution(self):
        self.assertIs(family_for_variant("ideogram4"), IDEOGRAM4)
        self.assertIs(family_for_train_type("ideogram4-lora"), IDEOGRAM4)
        self.assertIs(family_for_train_type("krea2-lora"), KREA2)
        # Unknown/empty values keep the pack's original Krea 2 default.
        self.assertIs(family_for_train_type("nope"), KREA2)
        self.assertIs(family_for_variant(None), KREA2)

    def test_family_scripts_and_modules(self):
        self.assertEqual(IDEOGRAM4.network_module, "musubi_tuner.networks.lora_ideogram4")
        self.assertEqual(IDEOGRAM4.cache_latents_script, "ideogram4_cache_latents.py")
        self.assertEqual(IDEOGRAM4.train_script, "ideogram4_train_network.py")
        self.assertFalse(IDEOGRAM4.supports_fp8_pair)
        self.assertEqual(IDEOGRAM4.blocks_to_swap_max, 33)


class AdapterIdeogram4Tests(unittest.TestCase):
    def adapt(self, root: Path, **overrides):
        config = ideogram4_config(root)
        config.update(overrides)
        return adapt_config(config, make_runtime(root), "run-id", family="ideogram4")

    def test_network_module_and_sampler_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "train").mkdir()
            adapted = self.adapt(root, sample_prompts=str(root / "prompts.txt"))

        self.assertEqual(adapted.values["network_module"], "musubi_tuner.networks.lora_ideogram4")
        self.assertEqual(adapted.values["sampler_preset"], "V4_DEFAULT_20")
        self.assertAlmostEqual(adapted.values["initial_sigma"], 1.004)
        self.assertEqual(adapted.values["network_dim"], 32)

    def test_no_sampler_defaults_without_prompts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "train").mkdir()
            adapted = self.adapt(root)

        self.assertNotIn("sampler_preset", adapted.values)
        self.assertNotIn("initial_sigma", adapted.values)

    def test_fp8_and_turbo_flags_are_dropped(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "train").mkdir()
            adapted = self.adapt(
                root,
                fp8_base=True,
                fp8_scaled=True,
                turbo_dit="./sd-models/krea2/krea2-turbo.safetensors",
                turbo_dit_cache=True,
            )

        for key in ("fp8_base", "fp8_scaled", "turbo_dit", "turbo_dit_cache"):
            self.assertNotIn(key, adapted.values)
        warnings = "\n".join(adapted.warnings)
        self.assertIn("Ideogram 4", warnings)
        self.assertIn("FP8", warnings)
        self.assertIn("turbo_dit", warnings)

    def test_unsupported_fields_raise(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "train").mkdir()
            with self.assertRaises(AdapterError):
                self.adapt(root, blocks_to_swap=40)

    def test_weighting_scheme_is_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "train").mkdir()
            adapted = self.adapt(root, weighting_scheme="sigmoid")

        self.assertNotIn("weighting_scheme", adapted.values)
        self.assertIn("weighting_scheme", "\n".join(adapted.warnings))

    def test_unconditional_dit_requires_optin_for_sampling(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "train").mkdir()
            unconditional = root / "uncond.safetensors"
            unconditional.write_text("", encoding="utf-8")
            adapted = self.adapt(root, unconditional_dit=str(unconditional), use_unconditional_dit_for_lora_sampling=True)
            informative = self.adapt(root, unconditional_dit=str(unconditional))
            with self.assertRaises(AdapterError):
                self.adapt(root, use_unconditional_dit_for_lora_sampling=True)

        self.assertTrue(adapted.values["use_unconditional_dit_for_lora_sampling"])
        self.assertIn("unconditional_dit", informative.values)
        self.assertIn("use_unconditional_dit_for_lora_sampling", "\n".join(informative.warnings))

    def test_fp16_is_coerced_to_bf16(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "train").mkdir()
            adapted = self.adapt(root, mixed_precision="fp16")

        self.assertEqual(adapted.values["mixed_precision"], "bf16")
        self.assertIn("Ideogram 4", "\n".join(adapted.warnings))

    def test_krea2_fp8_pair_behaviour_is_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "train").mkdir()
            config = {
                "model_train_type": "krea2-lora",
                "dit": "./sd-models/krea2/krea2.safetensors",
                "vae": "./sd-models/krea2/qwen_image_vae.safetensors",
                "text_encoder": "./sd-models/krea2/qwen3_vl_4b.safetensors",
                "train_data_dir": str(root / "train"),
                "fp8_base": True,
            }
            adapted = adapt_config(config, make_runtime(root), "run-id", family="krea2")

        self.assertTrue(adapted.values["fp8_base"])
        self.assertTrue(adapted.values["fp8_scaled"])

    def test_missing_model_field_uses_family_label(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "train").mkdir()
            with self.assertRaises(AdapterError) as ctx:
                self.adapt(root, text_encoder="")

        self.assertIn("Qwen3-VL-8B", str(ctx.exception))

    def test_cache_extra_args_per_stage(self):
        values = {
            "vae_dtype": "bfloat16",
            "text_cache_dtype": "fp8_e4m3fn",
            "validate_caption_structure": True,
            "warn_on_caption_issues": False,
        }
        self.assertEqual(cache_extra_args(IDEOGRAM4, "cache_latents", values), ["--vae_dtype", "bfloat16"])
        self.assertEqual(
            cache_extra_args(IDEOGRAM4, "cache_text_encoder", values),
            ["--text_cache_dtype", "fp8_e4m3fn", "--validate_caption_structure"],
        )
        self.assertEqual(cache_extra_args(KREA2, "cache_text_encoder", values), [])

    def test_cache_only_fields_stay_out_of_the_train_toml(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "train").mkdir()
            adapted = self.adapt(
                root,
                vae_dtype="bfloat16",
                text_cache_dtype="fp8_e4m3fn",
                validate_caption_structure=True,
                dit_dtype="bfloat16",
            )
            toml_text = dump_train_toml(adapted.values)

        # text_cache_dtype is cache-stage only; the rest must reach the train TOML
        # (vae_dtype also drives the sampling VAE load upstream).
        self.assertNotIn("text_cache_dtype", toml_text)
        for key in ("vae_dtype", "validate_caption_structure", "dit_dtype"):
            self.assertIn(key, toml_text)


class LauncherIdeogram4Tests(unittest.TestCase):
    def test_script_names_follow_family(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            dataset_toml = root / "dataset.toml"
            train_toml = root / "train.toml"
            train_toml.write_text('mixed_precision = "bf16"\n', encoding="utf-8")

            latents = build_cache_latents_spec(runtime, dataset_toml, "/models/vae.safetensors", "t", family="ideogram4")
            te = build_cache_text_encoder_spec(runtime, dataset_toml, "/models/te.safetensors", "t", family="ideogram4")
            train = build_train_spec(runtime, train_toml, "t", family="ideogram4")
            krea2_train = build_train_spec(runtime, train_toml, "t", family="krea2")

        self.assertTrue(latents.command[1].endswith("ideogram4_cache_latents.py"))
        self.assertTrue(te.command[1].endswith("ideogram4_cache_text_encoder_outputs.py"))
        self.assertTrue(any(part.endswith("ideogram4_train_network.py") for part in train.command))
        self.assertTrue(any(part.endswith("krea2_train_network.py") for part in krea2_train.command))

    def test_cache_stage_extra_args_are_appended(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            latents = build_cache_latents_spec(
                runtime,
                root / "dataset.toml",
                "/models/vae.safetensors",
                "t",
                family="ideogram4",
                extra_args=["--vae_dtype", "bfloat16"],
            )

        self.assertIn("--vae_dtype", latents.command)
        self.assertEqual(latents.command[latents.command.index("--vae_dtype") + 1], "bfloat16")


class PreflightIdeogram4Tests(unittest.TestCase):
    def test_missing_scripts_error_mentions_family_and_repair(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            runtime.musubi_root.mkdir(parents=True)
            runtime.python.parent.mkdir(parents=True)
            runtime.python.write_text("", encoding="utf-8")
            result = run_preflight({}, runtime, None, probe_with(), family="ideogram4")

        self.assertFalse(result.ok)
        joined = "\n".join(result.errors)
        self.assertIn("Ideogram 4", joined)
        self.assertIn("修复", joined)

    def test_tokenizer_missing_warns_for_ideogram4(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            write_runtime_files(runtime)
            models = root / "models"
            models.mkdir()
            values = {}
            for key in ("dit", "vae", "text_encoder"):
                path = models / f"{key}.safetensors"
                path.write_text("", encoding="utf-8")
                values[key] = str(path)
            result = run_preflight(values, runtime, None, probe_with(), family="ideogram4")

        self.assertTrue(result.ok, result.errors)
        joined = "\n".join(result.warnings)
        self.assertIn("tokenizer", joined.lower())
        self.assertIn("Hugging Face", joined)

    def test_low_vram_hint_is_family_specific(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            write_runtime_files(runtime)
            models = root / "models"
            models.mkdir()
            values = {}
            for key in ("dit", "vae", "text_encoder"):
                path = models / f"{key}.safetensors"
                path.write_text("", encoding="utf-8")
                values[key] = str(path)
            result = run_preflight(values, runtime, None, probe_with(vram_mb=8192), family="ideogram4")

        joined = "\n".join(result.warnings)
        self.assertIn(IDEOGRAM4.vram_hint.split("，")[0], joined)

    def test_unconditional_dit_must_exist(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = make_runtime(root)
            write_runtime_files(runtime)
            models = root / "models"
            models.mkdir()
            values = {}
            for key in ("dit", "vae", "text_encoder"):
                path = models / f"{key}.safetensors"
                path.write_text("", encoding="utf-8")
                values[key] = str(path)
            values["unconditional_dit"] = str(models / "missing.safetensors")
            result = run_preflight(values, runtime, None, probe_with(), family="ideogram4")

        self.assertFalse(result.ok)
        self.assertIn("unconditional", "\n".join(result.errors))


class Ideogram4PatchTests(unittest.TestCase):
    ROTARY_ANCHOR = "    _materialize_meta_tensors(model)"
    TOKENIZER_LINE = "    return AutoTokenizer.from_pretrained(QWEN3_VL_8B_INSTRUCT_REPO_ID)"

    def _write_module(self, root: Path) -> Path:
        module = root / "src" / "musubi_tuner" / "ideogram4" / "ideogram4_utils.py"
        module.parent.mkdir(parents=True, exist_ok=True)
        module.write_text(
            "def load_ideogram4_text_encoder(config, state_dict):\n"
            "    model = build(config)\n"
            f"{self.ROTARY_ANCHOR}\n"
            "    return model\n"
            "\n"
            "\n"
            "def load_ideogram4_tokenizer():\n"
            f"{self.TOKENIZER_LINE}\n",
            encoding="utf-8",
        )
        return module

    def _write_tokenizer_dir(self, root: Path, name: str = "qwen3-vl-8b-tokenizer") -> Path:
        tokenizer_dir = root / "sd-models" / "ideogram4" / name
        tokenizer_dir.mkdir(parents=True, exist_ok=True)
        (tokenizer_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
        (tokenizer_dir / "tokenizer_config.json").write_text("{}", encoding="utf-8")
        return tokenizer_dir

    def test_patch_sets_rotary_and_tokenizer(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            module = self._write_module(root)
            tokenizer_dir = self._write_tokenizer_dir(root)

            first = patch_ideogram4_source(root, tokenizer_dir, log=lambda _line: None)
            second = patch_ideogram4_source(root, tokenizer_dir, log=lambda _line: None)
            text = module.read_text(encoding="utf-8")
            compile(text, str(module), "exec")

        self.assertTrue(first)
        self.assertFalse(second, "patch must be idempotent")
        self.assertIn("rotary_emb = type(_rotary)(config.text_config", text)
        self.assertIn(tokenizer_dir.as_posix(), text)
        self.assertNotIn(self.TOKENIZER_LINE, text)

    def test_patch_without_tokenizer_dir_only_fixes_rotary(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            module = self._write_module(root)

            patched = patch_ideogram4_source(root, root / "missing-tokenizer", log=lambda _line: None)
            text = module.read_text(encoding="utf-8")

        self.assertTrue(patched)
        self.assertIn("_rotary = model.language_model.rotary_emb", text)
        self.assertIn(self.TOKENIZER_LINE, text)

    def test_patch_skips_missing_source(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.assertFalse(patch_ideogram4_source(root, root / "nope", log=lambda _line: None))

    def test_module_without_anchors_is_left_untouched(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            module = root / "src" / "musubi_tuner" / "ideogram4" / "ideogram4_utils.py"
            module.parent.mkdir(parents=True, exist_ok=True)
            module.write_text("def other():\n    return 1\n", encoding="utf-8")
            original = module.read_text(encoding="utf-8")

            patched = patch_ideogram4_source(root, root / "nope", log=lambda _line: None)
            after = module.read_text(encoding="utf-8")

        self.assertFalse(patched)
        self.assertEqual(after, original)

    def test_tokenizer_patch_follows_and_reverts_with_the_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            module = self._write_module(root)
            first_dir = self._write_tokenizer_dir(root, "first")
            second_dir = self._write_tokenizer_dir(root, "second")

            patch_ideogram4_source(root, first_dir, log=lambda _line: None)
            text_first = module.read_text(encoding="utf-8")
            patch_ideogram4_source(root, second_dir, log=lambda _line: None)
            text_second = module.read_text(encoding="utf-8")

            (second_dir / "tokenizer.json").unlink()
            patch_ideogram4_source(root, second_dir, log=lambda _line: None)
            text_reverted = module.read_text(encoding="utf-8")

        self.assertIn(first_dir.as_posix(), text_first)
        self.assertIn(second_dir.as_posix(), text_second)
        self.assertNotIn(first_dir.as_posix(), text_second)
        self.assertIn(self.TOKENIZER_LINE, text_reverted)
        self.assertIn("rotary_emb = type(_rotary)(config.text_config", text_reverted)


class Ideogram4AssetsTests(unittest.TestCase):
    def test_asset_manifest(self):
        assets = {asset.key: asset for asset in manifest_for("ideogram4-lora")}

        self.assertEqual(
            assets["dit"].hf_file, "diffusion_models/ideogram4_fp8_scaled.safetensors"
        )
        self.assertEqual(
            assets["unconditional_dit"].hf_file,
            "diffusion_models/ideogram4_unconditional_fp8_scaled.safetensors",
        )
        self.assertTrue(assets["unconditional_dit"].optional)
        self.assertEqual(assets["vae"].hf_file, "vae/flux2-vae.safetensors")
        self.assertEqual(assets["tokenizer"].kind, "dir")
        self.assertIn("非商用", assets["dit"].label)

    def test_tokenizer_dir_resolution(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.assertEqual(
                tokenizer_dir_for("ideogram4-lora", root),
                (root / "sd-models" / "ideogram4" / "qwen3-vl-8b-tokenizer").resolve(),
            )

    def test_both_download_sources_are_configured(self):
        with tempfile.TemporaryDirectory() as td:
            items = {item["key"]: item for item in check_assets("ideogram4-lora", {}, Path(td))}

        # The assets dialog defaults to ModelScope; a missing mirror makes the
        # whole batch fail, so every required asset needs both sources.
        for key in ("dit", "unconditional_dit", "text_encoder", "vae", "tokenizer"):
            self.assertTrue(items[key]["sources"]["huggingface"], key)
            self.assertTrue(items[key]["sources"]["modelscope"], key)


class Ideogram4ConfigImportTests(unittest.TestCase):
    def test_detects_ideogram4_config(self):
        analysis = analyze_train_type(
            {
                "dit": "/models/sd-models/ideogram4/ideogram4_fp8_scaled.safetensors",
                "text_encoder": "/models/sd-models/ideogram4/qwen3vl_8b_fp8_scaled.safetensors",
                "network_module": "musubi_tuner.networks.lora_ideogram4",
                "sampler_preset": "V4_DEFAULT_20",
            }
        )
        self.assertEqual(analysis.train_type, "ideogram4-lora")

    def test_still_detects_krea2_config(self):
        analysis = analyze_train_type(
            {
                "dit": "/models/sd-models/krea2/krea2.safetensors",
                "text_encoder": "/models/sd-models/krea2/qwen3_vl_4b.safetensors",
                "network_module": "musubi_tuner.networks.lora_krea2",
                "fp8_scaled": True,
            }
        )
        self.assertEqual(analysis.train_type, "krea2-lora")

    def test_page_spec_and_target_registered(self):
        self.assertEqual(PAGE_SPECS["ideogram4-lora"]["default_train_type"], "ideogram4-lora")
        self.assertEqual(TRAIN_TYPE_TARGETS["ideogram4-lora"]["path"], "/lora/ideogram4.html")


class DispatchGuardTests(unittest.TestCase):
    def test_unknown_family_variant_fails_loudly(self):
        from mikazuki.engines.musubi.run import handle_run
        from mikazuki.engines.runner import RunContext

        result = handle_run({}, RunContext(timestamp="t", autosave_dir=".", variant="ideogram4x"))

        self.assertEqual(result.status, "fail")
        self.assertIn("未注册的 musubi 模型族", result.message)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mikazuki.model_assets import (
    AssetDef,
    check_assets,
    download_assets,
    krea2_tokenizer_dir,
    manifest_for,
    patch_krea2_tokenizer_path,
    resolve_train_type,
)


class ModelAssetsManifestTests(unittest.TestCase):
    def test_krea2_manifest_has_required_assets(self):
        keys = [asset.key for asset in manifest_for("krea2-lora")]
        self.assertEqual(keys, ["dit", "vae", "text_encoder", "turbo_dit", "tokenizer"])

    def test_krea2_manifest_has_configured_sources(self):
        for asset in manifest_for("krea2-lora"):
            self.assertTrue(asset.hf_repo, asset.key)
            self.assertTrue(asset.ms_repo, asset.key)

    def test_unknown_train_type_has_empty_manifest(self):
        self.assertEqual(manifest_for("sd15-lora"), [])

    def test_klein_manifests_have_dit_and_vae(self):
        for train_type, dit_file in (
            ("klein-4b-lora", "flux-2-klein-base-4b.safetensors"),
            ("klein-9b-lora", "flux-2-klein-base-9b.safetensors"),
        ):
            assets = {asset.key: asset for asset in manifest_for(train_type)}
            self.assertEqual(set(assets), {"dit", "vae"})
            self.assertEqual(assets["dit"].hf_file, dit_file)
            self.assertTrue(assets["dit"].ms_repo, "ModelScope mirror for DiT")
            self.assertFalse(assets["dit"].optional)
            # VAE: HF + ModelScope (KanKanKan/flux2-vae mirror), required
            self.assertEqual(assets["vae"].hf_repo, "ai-toolkit/flux2_vae")
            self.assertEqual(assets["vae"].ms_repo, "KanKanKan/flux2-vae")
            self.assertEqual(assets["vae"].ms_file, "flux2-vae.safetensors")
            self.assertFalse(assets["vae"].optional)

    def test_klein_vae_lands_next_to_dit(self):
        # ai-toolkit auto-loads <name_or_path>/ae.safetensors: dit and vae defaults
        # must share the parent dir.
        assets = {asset.key: asset for asset in manifest_for("klein-4b-lora")}
        self.assertEqual(str(Path(assets["dit"].default_path).parent), str(Path(assets["vae"].default_path).parent))

    def test_resolve_train_type_prefers_config_value(self):
        self.assertEqual(resolve_train_type("lora-master", {"model_train_type": "krea2-lora"}), "krea2-lora")
        self.assertEqual(resolve_train_type("krea2-lora", {}), "krea2-lora")


class ModelAssetsCheckTests(unittest.TestCase):
    def test_check_reports_missing_and_existing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            existing = root / "models" / "dit.safetensors"
            existing.parent.mkdir(parents=True)
            existing.write_text("x", encoding="utf-8")
            items = check_assets("krea2-lora", {"dit": "models/dit.safetensors"}, root)
            by_key = {item["key"]: item for item in items}
            self.assertTrue(by_key["dit"]["exists"])
            self.assertEqual(by_key["dit"]["path"], str(existing.resolve()))
            self.assertFalse(by_key["vae"]["exists"])
            self.assertFalse(by_key["text_encoder"]["exists"])
            self.assertFalse(by_key["tokenizer"]["exists"])
            self.assertTrue(by_key["turbo_dit"]["optional"])

    def test_check_marks_sources_configured_for_krea2(self):
        with tempfile.TemporaryDirectory() as td:
            items = check_assets("krea2-lora", {}, Path(td))
            for item in items:
                self.assertTrue(item["sources"]["huggingface"], item["key"])
                self.assertTrue(item["sources"]["modelscope"], item["key"])

    def test_tokenizer_dir_complete_when_required_files_present(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tokenizer_dir = root / "sd-models/krea2/qwen3-vl-tokenizer"
            tokenizer_dir.mkdir(parents=True)
            (tokenizer_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
            (tokenizer_dir / "tokenizer_config.json").write_text("{}", encoding="utf-8")
            items = check_assets("krea2-lora", {}, root)
            tokenizer = next(item for item in items if item["key"] == "tokenizer")
            self.assertTrue(tokenizer["exists"])
            self.assertEqual(tokenizer["path"], str(tokenizer_dir.resolve()))


class ModelAssetsDownloadTests(unittest.TestCase):
    def test_download_via_huggingface(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            def fake_hf_download(repo_id, filename, local_dir):
                target = Path(local_dir) / filename
                target.write_text("weights", encoding="utf-8")
                return str(target)

            with mock.patch("mikazuki.model_assets.manifest_for") as manifest, \
                 mock.patch("huggingface_hub.hf_hub_download", side_effect=fake_hf_download):
                manifest.return_value = [
                    AssetDef("dit", "DiT", "sd-models/krea2/krea2.safetensors", hf_repo="org/repo", hf_file="krea2.safetensors")
                ]
                logs = []
                download_assets("krea2-lora", [{"key": "dit"}], "huggingface", root, logs.append)

            self.assertEqual((root / "sd-models/krea2/krea2.safetensors").read_text(encoding="utf-8"), "weights")
            self.assertTrue(any("huggingface org/repo" in line for line in logs))

    def test_download_rejects_unconfigured_source(self):
        with tempfile.TemporaryDirectory() as td, mock.patch("mikazuki.model_assets.manifest_for") as manifest:
            manifest.return_value = [AssetDef("dit", "DiT", "x.safetensors", hf_repo="org/repo", hf_file="f.safetensors")]
            with self.assertRaises(ValueError):
                download_assets("krea2-lora", [{"key": "dit"}], "modelscope", Path(td), lambda line: None)

    def test_download_tokenizer_dir_via_huggingface(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            def fake_hf_download(repo_id, filename, local_dir):
                target = Path(local_dir) / filename
                target.write_text("{}", encoding="utf-8")
                return str(target)

            with mock.patch("huggingface_hub.hf_hub_download", side_effect=fake_hf_download), \
                 mock.patch("mikazuki.model_assets.patch_krea2_tokenizer_everywhere") as patch:
                logs = []
                download_assets("krea2-lora", [{"key": "tokenizer"}], "huggingface", root, logs.append)

            tokenizer_dir = krea2_tokenizer_dir(root)
            self.assertTrue((tokenizer_dir / "tokenizer.json").is_file())
            self.assertTrue((tokenizer_dir / "merges.txt").is_file())
            patch.assert_called_once()


class Krea2TokenizerPatchTests(unittest.TestCase):
    ENCODER = (
        '"""encoder"""\n'
        "def load_qwen3_vl_conditioner(model_path, tokenizer_repo, max_length):\n"
        "    tokenizer = AutoTokenizer.from_pretrained(tokenizer_repo, max_length=max_length)\n"
        "    processor = Qwen2TokenizerFast.from_pretrained(tokenizer_repo, max_length=max_length)\n"
    )

    def _layout(self, root: Path, with_tokenizer: bool = True) -> tuple[Path, Path]:
        tokenizer_dir = root / "tokenizer"
        if with_tokenizer:
            tokenizer_dir.mkdir(parents=True)
            (tokenizer_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
            (tokenizer_dir / "tokenizer_config.json").write_text("{}", encoding="utf-8")
        source_root = root / "musubi"
        encoder_dir = source_root / "src" / "musubi_tuner" / "krea2"
        encoder_dir.mkdir(parents=True, exist_ok=True)
        (encoder_dir / "krea2_encoder.py").write_text(self.ENCODER, encoding="utf-8")
        return source_root, tokenizer_dir

    def test_patch_injects_local_tokenizer_dir_once(self):
        with tempfile.TemporaryDirectory() as td:
            source_root, tokenizer_dir = self._layout(Path(td))
            logs = []
            self.assertTrue(patch_krea2_tokenizer_path(source_root, tokenizer_dir, logs.append))
            encoder = source_root / "src" / "musubi_tuner" / "krea2" / "krea2_encoder.py"
            text = encoder.read_text(encoding="utf-8")
            self.assertIn(f'from_pretrained(r"{tokenizer_dir.as_posix()}"', text)
            self.assertNotIn("from_pretrained(tokenizer_repo", text)
            compile(text, str(encoder), "exec")
            self.assertTrue(patch_krea2_tokenizer_path(source_root, tokenizer_dir, logs.append))
            self.assertEqual(encoder.read_text(encoding="utf-8").count("mikazuki: patched tokenizer path"), 2)

    def test_patch_noop_without_tokenizer_files(self):
        with tempfile.TemporaryDirectory() as td:
            source_root, tokenizer_dir = self._layout(Path(td), with_tokenizer=False)
            self.assertFalse(patch_krea2_tokenizer_path(source_root, tokenizer_dir, lambda line: None))
            encoder = source_root / "src" / "musubi_tuner" / "krea2" / "krea2_encoder.py"
            self.assertEqual(encoder.read_text(encoding="utf-8"), self.ENCODER)


if __name__ == "__main__":
    unittest.main()

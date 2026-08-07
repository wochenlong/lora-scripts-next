from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mikazuki.model_assets import (
    AssetDef,
    check_assets,
    download_assets,
    manifest_for,
    resolve_train_type,
    _hf_cache_complete,
    _materialize_hf_cache,
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
            self.assertTrue(by_key["turbo_dit"]["optional"])

    def test_check_marks_sources_configured_for_krea2(self):
        with tempfile.TemporaryDirectory() as td:
            items = check_assets("krea2-lora", {}, Path(td))
            for item in items:
                self.assertTrue(item["sources"]["huggingface"], item["key"])
                self.assertTrue(item["sources"]["modelscope"], item["key"])


class ModelAssetsHfCacheTests(unittest.TestCase):
    def test_materialize_hf_cache_makes_repo_complete(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch("huggingface_hub.constants.HF_HUB_CACHE", str(Path(td) / "hub")):
            source = Path(td) / "ms"
            source.mkdir()
            (source / "tokenizer.json").write_text("{}", encoding="utf-8")
            (source / "tokenizer_config.json").write_text("{}", encoding="utf-8")
            logs = []
            _materialize_hf_cache("Qwen/Qwen3-VL-4B-Instruct", source, logs.append)
            self.assertTrue(_hf_cache_complete("Qwen/Qwen3-VL-4B-Instruct"))
            snapshots = list((Path(td) / "hub" / "models--Qwen--Qwen3-VL-4B-Instruct" / "snapshots").iterdir())
            self.assertEqual(len(snapshots), 1)
            self.assertRegex(snapshots[0].name, r"^[0-9a-f]{40}$")
            self.assertTrue((snapshots[0] / "tokenizer.json").is_file())
            ref = (Path(td) / "hub" / "models--Qwen--Qwen3-VL-4B-Instruct" / "refs" / "main").read_text(encoding="utf-8")
            self.assertEqual(ref, snapshots[0].name)

    def test_hf_cache_check_reports_missing(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch("huggingface_hub.constants.HF_HUB_CACHE", str(Path(td) / "hub")):
            items = check_assets("krea2-lora", {}, Path(td))
            tokenizer = next(item for item in items if item["key"] == "tokenizer")
            self.assertFalse(tokenizer["exists"])


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
                from mikazuki.model_assets import AssetDef
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


if __name__ == "__main__":
    unittest.main()

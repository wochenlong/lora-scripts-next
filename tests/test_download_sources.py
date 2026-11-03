from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

from mikazuki.download_sources import (
    DownloadSources,
    apply_github_prefix,
    install_process_env,
    parse_download_sources,
    pytorch_extra_index_url,
)


class DownloadSourcesTests(unittest.TestCase):
    def test_parse_flat_payload(self):
        sources = parse_download_sources(
            {
                "dry_run": False,
                "pip_index_url": "https://pypi.tuna.tsinghua.edu.cn/simple",
                "pytorch_index_url": "https://mirrors.aliyun.com/pytorch-wheels",
                "hf_endpoint": "https://hf-mirror.com",
                "github_url_prefix": "https://ghfast.top/",
            }
        )
        self.assertIsNotNone(sources)
        assert sources is not None
        self.assertEqual(sources.pip_index_url, "https://pypi.tuna.tsinghua.edu.cn/simple")
        self.assertEqual(sources.github_url_prefix, "https://ghfast.top/")

    def test_parse_nested_payload(self):
        sources = parse_download_sources(
            {"download_sources": {"hf_endpoint": "https://huggingface.co", "pip_index_url": ""}}
        )
        self.assertEqual(sources, DownloadSources(hf_endpoint="https://huggingface.co"))

    def test_parse_empty_returns_none(self):
        self.assertIsNone(parse_download_sources({"dry_run": False}))
        self.assertIsNone(parse_download_sources({"pip_index_url": "  "}))

    def test_apply_github_prefix(self):
        url = "https://github.com/kohya-ss/musubi-tuner.git"
        self.assertEqual(apply_github_prefix(url, None), url)
        self.assertEqual(
            apply_github_prefix(url, "https://ghfast.top"),
            "https://ghfast.top/https://github.com/kohya-ss/musubi-tuner.git",
        )
        prefixed = "https://ghfast.top/" + url
        self.assertEqual(apply_github_prefix(url, "https://ghfast.top/"), prefixed)
        self.assertEqual(apply_github_prefix(prefixed, "https://ghfast.top/"), prefixed)

    def test_pytorch_extra_index_appends_cuda_tag(self):
        self.assertEqual(
            pytorch_extra_index_url("https://mirrors.aliyun.com/pytorch-wheels", "cu128", "fallback"),
            "https://mirrors.aliyun.com/pytorch-wheels/cu128",
        )
        self.assertEqual(
            pytorch_extra_index_url("https://download.pytorch.org/whl/cu130", "cu128", "fallback"),
            "https://download.pytorch.org/whl/cu130",
        )
        self.assertEqual(
            pytorch_extra_index_url(None, "cu128", "https://download.pytorch.org/whl/cu128"),
            "https://download.pytorch.org/whl/cu128",
        )

    def test_parse_proxy_url(self):
        sources = parse_download_sources({"proxy_url": "http://127.0.0.1:7890"})
        self.assertEqual(sources, DownloadSources(proxy_url="http://127.0.0.1:7890"))

    def test_install_process_env_with_proxy_covers_both_cases(self):
        env = install_process_env(DownloadSources(proxy_url="http://127.0.0.1:7890"))
        self.assertIsNotNone(env)
        assert env is not None
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            self.assertEqual(env[key], "http://127.0.0.1:7890")
        self.assertNotIn("HF_ENDPOINT", env)

    def test_install_process_env_without_source_overrides_uses_network_policy(self):
        for sources in (None, DownloadSources()):
            env = install_process_env(sources)
            self.assertNotIn("HF_ENDPOINT", env)
            self.assertIn("HTTP_PROXY", env)
            self.assertIn("HTTPS_PROXY", env)


class DownloadSourcesPersistenceTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        from mikazuki import download_sources as module

        self._module = module
        self.config = Path(self._tmp.name) / "download-sources.local.json"
        self._patch = mock.patch.object(module, "config_path", return_value=self.config)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_load_missing_file_returns_none(self):
        from mikazuki.download_sources import load_download_sources

        self.assertIsNone(load_download_sources())

    def test_save_then_load_roundtrip_preserves_credentials(self):
        from mikazuki.download_sources import load_download_sources, save_download_sources

        sources = DownloadSources(
            pip_index_url="https://user:secret@pypi.example.com/simple",
            hf_endpoint="https://hf-mirror.com",
            proxy_url="http://127.0.0.1:7890",
        )
        save_download_sources(sources)
        self.assertEqual(load_download_sources(), sources)

    def test_save_none_removes_file(self):
        from mikazuki.download_sources import load_download_sources, save_download_sources

        save_download_sources(DownloadSources(hf_endpoint="https://hf-mirror.com"))
        self.assertTrue(self.config.is_file())
        save_download_sources(None)
        self.assertFalse(self.config.exists())
        self.assertIsNone(load_download_sources())

    def test_resolve_prefers_payload_over_saved(self):
        from mikazuki.download_sources import resolve_download_sources, save_download_sources

        save_download_sources(DownloadSources(hf_endpoint="https://hf-mirror.com"))
        resolved = resolve_download_sources({"hf_endpoint": "https://huggingface.co"})
        self.assertEqual(resolved, DownloadSources(hf_endpoint="https://huggingface.co"))

    def test_resolve_falls_back_to_saved_then_none(self):
        from mikazuki.download_sources import resolve_download_sources, save_download_sources

        save_download_sources(DownloadSources(hf_endpoint="https://hf-mirror.com", proxy_url="http://127.0.0.1:7890"))
        self.assertEqual(
            resolve_download_sources({"dry_run": True}),
            DownloadSources(hf_endpoint="https://hf-mirror.com", proxy_url="http://127.0.0.1:7890"),
        )
        save_download_sources(None)
        self.assertIsNone(resolve_download_sources({}))
        self.assertIsNone(resolve_download_sources(None))


class DownloadSourcesApiTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        from mikazuki import download_sources as module

        self.config = Path(self._tmp.name) / "download-sources.local.json"
        self._patch = mock.patch.object(module, "config_path", return_value=self.config)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def _client(self):
        from fastapi.testclient import TestClient
        from mikazuki.app.application import app

        return TestClient(app)

    def test_get_reports_unconfigured(self):
        data = self._client().get("/api/download-sources").json()
        self.assertEqual(data["status"], "success")
        self.assertFalse(data["data"]["configured"])
        self.assertIsNone(data["data"]["sources"])

    def test_put_then_get_roundtrip(self):
        client = self._client()
        payload = {"hf_endpoint": "https://hf-mirror.com", "proxy_url": "http://127.0.0.1:7890"}
        saved = client.put("/api/download-sources", json=payload).json()
        self.assertEqual(saved["status"], "success")
        self.assertTrue(saved["data"]["configured"])
        fetched = client.get("/api/download-sources").json()
        self.assertEqual(fetched["data"]["sources"]["hf_endpoint"], "https://hf-mirror.com")

    def test_put_rejects_non_http_url(self):
        response = self._client().put("/api/download-sources", json={"hf_endpoint": "file:///etc/passwd"}).json()
        self.assertEqual(response["status"], "fail")
        self.assertFalse(self.config.exists())

    def test_put_empty_clears_config(self):
        client = self._client()
        client.put("/api/download-sources", json={"hf_endpoint": "https://hf-mirror.com"})
        cleared = client.put("/api/download-sources", json={}).json()
        self.assertEqual(cleared["status"], "success")
        self.assertFalse(cleared["data"]["configured"])
        self.assertFalse(self.config.exists())


if __name__ == "__main__":
    unittest.main()

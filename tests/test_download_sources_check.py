from __future__ import annotations

import asyncio
import unittest
import urllib.error
from unittest import mock

from mikazuki.download_sources import DownloadSources
from mikazuki.download_sources_check import (
    DEFAULT_HF_ENDPOINT,
    DEFAULT_PIP_INDEX_URL,
    GITHUB_PROBE_URL,
    _probe,
    check_download_sources,
    probe_targets,
)


class _FakeResponse:
    def __init__(self, status: int = 200):
        self.status = status

    def read(self, _size: int = -1) -> bytes:
        return b"{}"

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class ProbeTargetsTests(unittest.TestCase):
    def test_defaults_when_sources_omitted(self):
        targets = probe_targets(None)
        self.assertEqual(targets["pip"], f"{DEFAULT_PIP_INDEX_URL}/")
        self.assertIn("/cu128/", targets["pytorch"])
        self.assertTrue(targets["pytorch"].startswith("https://download.pytorch.org/whl"))
        self.assertEqual(targets["huggingface"], f"{DEFAULT_HF_ENDPOINT}/api/models?limit=1")
        self.assertEqual(targets["github"], GITHUB_PROBE_URL)

    def test_partial_sources_mix_explicit_and_default(self):
        sources = DownloadSources(hf_endpoint="https://huggingface.co", github_url_prefix="https://ghfast.top/")
        targets = probe_targets(sources)
        self.assertEqual(targets["huggingface"], "https://huggingface.co/api/models?limit=1")
        self.assertEqual(targets["github"], f"https://ghfast.top/{GITHUB_PROBE_URL}")
        self.assertEqual(targets["pip"], f"{DEFAULT_PIP_INDEX_URL}/")

    def test_pytorch_base_without_cuda_suffix_gets_probe_tag(self):
        sources = DownloadSources(pytorch_index_url="https://mirrors.aliyun.com/pytorch-wheels")
        targets = probe_targets(sources)
        self.assertEqual(targets["pytorch"], "https://mirrors.aliyun.com/pytorch-wheels/cu128/")

    def test_pytorch_base_with_cuda_suffix_kept(self):
        sources = DownloadSources(pytorch_index_url="https://example.com/whl/cu124")
        targets = probe_targets(sources)
        self.assertEqual(targets["pytorch"], "https://example.com/whl/cu124/")


class ProbeTests(unittest.TestCase):
    def test_ok_on_2xx(self):
        with mock.patch("mikazuki.download_sources_check.urllib.request.urlopen", return_value=_FakeResponse(200)):
            result = _probe("https://pypi.org/simple/")
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], 200)
        self.assertIsNone(result["error"])
        self.assertIsInstance(result["latency_ms"], int)

    def test_http_error_not_ok_but_has_status(self):
        err = urllib.error.HTTPError("https://x", 503, "unavailable", None, None)
        with mock.patch("mikazuki.download_sources_check.urllib.request.urlopen", side_effect=err):
            result = _probe("https://pypi.org/simple/")
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], 503)

    def test_network_error_not_ok(self):
        with mock.patch(
            "mikazuki.download_sources_check.urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection reset"),
        ):
            result = _probe("https://pypi.org/simple/")
        self.assertFalse(result["ok"])
        self.assertIsNone(result["status"])
        self.assertIn("connection reset", result["error"])

    def test_rejects_non_http_scheme(self):
        result = _probe("file:///etc/passwd")
        self.assertFalse(result["ok"])
        self.assertIn("scheme", result["error"])

    def test_check_aggregates_all_channels(self):
        with mock.patch("mikazuki.download_sources_check._probe", return_value={"ok": True}):
            data = asyncio.run(check_download_sources(None))
        self.assertEqual(set(data), {"pip", "pytorch", "huggingface", "github"})
        self.assertTrue(all(entry["ok"] for entry in data.values()))

    def test_check_single_channel_only(self):
        with mock.patch("mikazuki.download_sources_check._probe", return_value={"ok": True}) as probe_mock:
            data = asyncio.run(check_download_sources(None, ["huggingface"]))
        self.assertEqual(set(data), {"huggingface"})
        self.assertEqual(probe_mock.call_count, 1)

    def test_check_ignores_unknown_channel_names(self):
        with mock.patch("mikazuki.download_sources_check._probe", return_value={"ok": True}):
            data = asyncio.run(check_download_sources(None, ["pip", "bogus"]))
        self.assertEqual(set(data), {"pip"})

    def test_proxy_url_uses_proxy_handler_opener(self):
        opener = mock.MagicMock()
        opener.open.return_value = _FakeResponse(200)
        proxies = {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}
        with mock.patch("mikazuki.download_sources_check.urllib.request.build_opener", return_value=opener) as build_mock:
            result = _probe("https://pypi.org/simple/", proxies=proxies)
        self.assertTrue(result["ok"])
        handler = build_mock.call_args.args[0]
        self.assertEqual(handler.proxies, proxies)

    def test_empty_proxy_map_disables_ambient_env_proxy(self):
        opener = mock.MagicMock()
        opener.open.return_value = _FakeResponse(200)
        with mock.patch("mikazuki.download_sources_check.urllib.request.build_opener", return_value=opener) as build_mock:
            result = _probe("https://pypi.org/simple/", proxies={})
        self.assertTrue(result["ok"])
        handler = build_mock.call_args.args[0]
        self.assertEqual(handler.proxies, {})

    def test_check_passes_proxy_to_every_channel(self):
        sources = DownloadSources(proxy_url="http://127.0.0.1:7890")
        with mock.patch("mikazuki.download_sources_check._probe", return_value={"ok": True}) as probe_mock:
            asyncio.run(check_download_sources(sources, ["pip", "github"]))
        for call in probe_mock.call_args_list:
            self.assertEqual(call.args[2], {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"})

    def test_check_uses_policy_proxies_without_override(self):
        policy = {"http": "http://policy-proxy:8080", "https": "http://policy-proxy:8080"}
        with mock.patch("mikazuki.download_sources_check._policy_proxies", return_value=policy), mock.patch(
            "mikazuki.download_sources_check._probe", return_value={"ok": True}
        ) as probe_mock:
            asyncio.run(check_download_sources(None, ["pip"]))
        self.assertEqual(probe_mock.call_args.args[2], policy)

    def test_direct_policy_proxies_ignore_ambient_env(self):
        from mikazuki.download_sources_check import _policy_proxies
        from mikazuki.networking.policy import NetworkPolicy

        # Pin the policy: auto mode intentionally accepts operator environment
        # proxies, whereas direct mode must prevent urllib from inheriting them.
        with mock.patch.dict("os.environ", {"http_proxy": "http://ambient:1", "https_proxy": "http://ambient:1"}), mock.patch(
            "mikazuki.networking.resolve_policy", return_value=NetworkPolicy(mode="direct", no_proxy="*"),
        ):
            proxies = _policy_proxies()
        self.assertEqual(proxies, {"no": "*"})

    def test_manual_policy_proxies_replace_ambient_env(self):
        from mikazuki.download_sources_check import _policy_proxies
        from mikazuki.networking.policy import NetworkPolicy

        policy = NetworkPolicy(mode="manual", http_proxy="http://policy:8080", https_proxy="http://policy:8080")
        with mock.patch.dict("os.environ", {"http_proxy": "http://ambient:1", "https_proxy": "http://ambient:1"}), mock.patch(
            "mikazuki.networking.resolve_policy", return_value=policy,
        ):
            proxies = _policy_proxies()
        self.assertEqual(proxies["http"], "http://policy:8080")
        self.assertEqual(proxies["https"], "http://policy:8080")


class ProbeTargetsEnvTests(unittest.TestCase):
    def test_hf_target_prefers_operator_hf_endpoint(self):
        with mock.patch.dict("os.environ", {"HF_ENDPOINT": "https://operator.example.com"}):
            targets = probe_targets(None)
        self.assertEqual(targets["huggingface"], "https://operator.example.com/api/models?limit=1")

    def test_hf_target_explicit_source_beats_env(self):
        sources = DownloadSources(hf_endpoint="https://huggingface.co")
        with mock.patch.dict("os.environ", {"HF_ENDPOINT": "https://operator.example.com"}):
            targets = probe_targets(sources)
        self.assertEqual(targets["huggingface"], "https://huggingface.co/api/models?limit=1")

if __name__ == "__main__":
    unittest.main()

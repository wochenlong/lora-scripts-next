"""anima-fast routes: manifest pin fallback for source_commit."""

import asyncio

from mikazuki.engines.anima_fast import routes
from mikazuki.engines.anima_fast.manifest import UPSTREAM


class _Runtime:
    source_commit = ""
    anima_root = None
    python = None
    output_dir = None
    logging_dir = None
    cache_dir = None


class _Plan:
    def as_dict(self):
        return {}


class _Status:
    state = "not_installed"

    def as_dict(self):
        return {}


def _patch_install_deps(monkeypatch, tmp_path, captured, runtime_source_commit=""):
    class _R(_Runtime):
        pass

    _R.source_commit = runtime_source_commit
    monkeypatch.setattr(routes, "anima_fast_runtime", lambda: _R())
    monkeypatch.setattr(routes, "default_layout", lambda root: None)
    monkeypatch.setattr(routes, "read_extension_status", lambda layout: _Status())
    monkeypatch.setattr(routes, "resolve_install_source_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(routes, "build_install_plan", lambda *a, **k: captured.update(k) or _Plan())


def test_install_falls_back_to_manifest_pin(monkeypatch, tmp_path):
    captured = {}
    _patch_install_deps(monkeypatch, tmp_path, captured, runtime_source_commit="")

    response = asyncio.run(routes.install({"dry_run": True}))

    assert response.status == "success"
    assert captured["source_commit"] == UPSTREAM["commit"]


def test_install_config_commit_beats_manifest_pin(monkeypatch, tmp_path):
    captured = {}
    _patch_install_deps(monkeypatch, tmp_path, captured, runtime_source_commit="1111111")

    response = asyncio.run(routes.install({"dry_run": True}))

    assert response.status == "success"
    assert captured["source_commit"] == "1111111"


def test_install_payload_commit_overrides_all(monkeypatch, tmp_path):
    captured = {}
    _patch_install_deps(monkeypatch, tmp_path, captured, runtime_source_commit="1111111")

    response = asyncio.run(routes.install({"dry_run": True, "source_commit": "deadbeef"}))

    assert response.status == "success"
    assert captured["source_commit"] == "deadbeef"

"""musubi routes: default upstream pin from the pack manifest."""

import asyncio

from mikazuki.engines.musubi import routes
from mikazuki.engines.musubi.manifest import UPSTREAM


def test_manifest_pin_is_full_sha():
    commit = UPSTREAM["commit"]
    assert len(commit) == 40
    assert all(c in "0123456789abcdef" for c in commit)


def test_install_falls_back_to_manifest_pin(monkeypatch, tmp_path):
    captured = {}

    class _Plan:
        def as_dict(self):
            return {}

    class _Status:
        state = "not_installed"

        def as_dict(self):
            return {}

    monkeypatch.setattr(routes, "resolve_musubi_install_source_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(routes, "musubi_default_layout", lambda root: None)
    monkeypatch.setattr(routes, "read_musubi_extension_status", lambda layout: _Status())
    monkeypatch.setattr(
        routes,
        "build_musubi_install_plan",
        lambda *a, **k: captured.update(k) or _Plan(),
    )

    response = asyncio.run(routes.install({"dry_run": True}))

    assert response.status == "success"
    assert captured["source_commit"] == UPSTREAM["commit"]


def test_install_payload_commit_overrides_pin(monkeypatch, tmp_path):
    captured = {}

    class _Plan:
        def as_dict(self):
            return {}

    class _Status:
        state = "not_installed"

        def as_dict(self):
            return {}

    monkeypatch.setattr(routes, "resolve_musubi_install_source_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(routes, "musubi_default_layout", lambda root: None)
    monkeypatch.setattr(routes, "read_musubi_extension_status", lambda layout: _Status())
    monkeypatch.setattr(
        routes,
        "build_musubi_install_plan",
        lambda *a, **k: captured.update(k) or _Plan(),
    )

    response = asyncio.run(routes.install({"dry_run": True, "source_commit": "deadbeef"}))

    assert response.status == "success"
    assert captured["source_commit"] == "deadbeef"

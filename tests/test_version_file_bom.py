"""V30 hardening: VERSION files written with a UTF-8 BOM (PowerShell 5.1
``Set-Content -Encoding UTF8`` / Notepad default) must not leak the BOM into
the host version string.

Observed in rc.4 live acceptance: a BOM-prefixed VERSION made
``version_satisfies`` raise ``TrustError: invalid version: \\ufeff3.0.0-rc.4``
during install, surfaced to users as a generic MARKETPLACE_TRUST_FAILED.
"""

from __future__ import annotations

from pathlib import Path

import pytest


BOM = b"\xef\xbb\xbf"


@pytest.fixture()
def fake_code_root(tmp_path: Path) -> Path:
    """Layout: <root>/VERSION + <root>/a/b/<module>.py mirroring __file__ chains."""
    (tmp_path / "a" / "b").mkdir(parents=True)
    return tmp_path


def test_host_version_strips_bom(monkeypatch, fake_code_root: Path):
    from mikazuki.plugin_marketplace import api

    api_file = fake_code_root / "a" / "b" / "api.py"
    api_file.write_text("pass", encoding="utf-8")
    (fake_code_root / "VERSION").write_bytes(BOM + b"3.0.0-rc.4\n")
    monkeypatch.setattr(api, "__file__", str(api_file))
    assert api._host_version() == "3.0.0-rc.4"


def test_host_version_plain_file_unchanged(monkeypatch, fake_code_root: Path):
    from mikazuki.plugin_marketplace import api

    api_file = fake_code_root / "a" / "b" / "api.py"
    api_file.write_text("pass", encoding="utf-8")
    (fake_code_root / "VERSION").write_bytes(b"3.0.0-rc.4\n")
    monkeypatch.setattr(api, "__file__", str(api_file))
    assert api._host_version() == "3.0.0-rc.4"


def test_host_version_missing_file_fallback(monkeypatch, fake_code_root: Path):
    from mikazuki.plugin_marketplace import api

    api_file = fake_code_root / "a" / "b" / "api.py"
    api_file.write_text("pass", encoding="utf-8")
    monkeypatch.setattr(api, "__file__", str(api_file))
    assert api._host_version() == "0.0.0"


def test_update_check_local_version_strips_bom(monkeypatch, fake_code_root: Path):
    import mikazuki.update_check as uc

    uc_file = fake_code_root / "a" / "update_check.py"
    uc_file.write_text("pass", encoding="utf-8")
    (fake_code_root / "VERSION").write_bytes(BOM + b"9.9.9-bom\n")
    monkeypatch.setattr(uc, "__file__", str(uc_file))
    assert uc.local_version() == "9.9.9-bom"

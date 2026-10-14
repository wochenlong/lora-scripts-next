"""Runtime initialization must use public seeds and preserve user dictionaries."""
from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from types import ModuleType

import pytest

from mikazuki.tag_translation import dictionary_bundle as bundle


def _database(path, text="蓝瞳"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE tags(name TEXT PRIMARY KEY,category INTEGER,cn_name TEXT,post_count INTEGER)")
        connection.execute("INSERT INTO tags VALUES('blue_eyes',0,?,100)", (text,))


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "fresh-project"
    source = root / "assets/tag_translation/danbooru"
    source.mkdir(parents=True)
    _database(source / "tag.sqlite")
    license_text = b"MIT License\nCopyright fixture\n"
    (source / "LICENSE.ffdkj.txt").write_bytes(license_text)
    sha = bundle.git_blob_sha(source / "tag.sqlite")
    manifest = {
        "version": 1, "source_url": "https://example.test/locked/tag.sqlite", "source_commit": "1" * 40,
        "git_blob_sha": sha, "sha256": hashlib.sha256((source / "tag.sqlite").read_bytes()).hexdigest(),
        "size_bytes": (source / "tag.sqlite").stat().st_size, "row_count": 1,
        "license": "MIT", "license_sha256": hashlib.sha256(license_text).hexdigest(),
    }
    (source / "source-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (source / "metadata.json").write_text(json.dumps({
        "installed_sha": sha, "remote_sha": sha, "download_url": manifest["source_url"],
        "remote_size": manifest["size_bytes"], "row_count": 1,
        "last_checked_at": "2026-10-13T00:00:00+00:00", "last_updated_at": "2026-10-13T00:00:00+00:00",
    }), encoding="utf-8")
    lock = tmp_path / "release-lock.json"
    lock.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(bundle, "DEFAULT_MANIFEST", lock)
    bundle.verify_bundle(source)
    return root, source


def _initialize(root, target_root, monkeypatch):
    # Execute the production initializer with a fresh __file__ and harmless
    # adapter constructors, avoiding the actual application's global state.
    for name, classes in {
        "translation_config": ("OnlineServiceConfig",),
        "translation_store": ("TranslationStore",),
        "translation_service": ("TranslationManager",),
    }.items():
        module = ModuleType(f"mikazuki.tag_translation.{name}")
        for class_name in classes:
            setattr(module, class_name, type(class_name, (), {"__init__": lambda self, *args, **kwargs: None}))
        monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setenv("MIKAZUKI_TAG_TRANSLATION_ROOT", str(target_root))
    monkeypatch.setenv("MIKAZUKI_BUNDLED_TAG_DICTIONARY_ROOT", str(root / "assets/tag_translation/danbooru"))
    namespace = {"__name__": "mikazuki.tag_translation.runtime_seed_probe", "__package__": "mikazuki.tag_translation",
                 "__file__": str(root / "mikazuki/tag_translation/runtime.py")}
    original = Path(__file__).resolve().parents[1] / "mikazuki/tag_translation/runtime.py"
    exec(compile(original.read_text(encoding="utf-8"), str(original), "exec"), namespace)
    service = namespace["dictionary_service"]
    service.session_factory = lambda **kwargs: (_ for _ in ()).throw(AssertionError("no startup network"))
    return service


def test_empty_external_root_receives_verified_public_dictionary(project, tmp_path, monkeypatch):
    root, source = project
    target_root = tmp_path / "empty-user-data"
    service = _initialize(root, target_root, monkeypatch)
    assert service.status()["installed"] is True
    assert asyncio.run(service.ensure("zh-CN"))["state"] == "ready"
    assert service.lookup(["blue_eyes"])["blue_eyes"]["text"] == "蓝瞳"
    assert {p.name for p in (target_root / "danbooru").iterdir()} == set(bundle.BUNDLE_FILES)
    assert (target_root / "danbooru/tag.sqlite").read_bytes() == (source / "tag.sqlite").read_bytes()


def test_updated_existing_user_dictionary_is_preserved_without_factory_hash(project, tmp_path, monkeypatch):
    root, _ = project
    target_root = tmp_path / "updated-user-data"
    target = target_root / "danbooru/tag.sqlite"
    _database(target, "用户新译文")
    before = target.read_bytes()
    service = _initialize(root, target_root, monkeypatch)
    assert service.status()["state"] == "ready"
    assert service.lookup(["blue_eyes"])["blue_eyes"]["text"] == "用户新译文"
    assert target.read_bytes() == before


@pytest.mark.parametrize("default_root", [False, True])
def test_corrupt_existing_dictionary_is_preserved_and_reported_without_network(project, tmp_path, monkeypatch, default_root):
    root, source = project
    target_root = source.parent if default_root else tmp_path / "corrupt-user-data"
    target = target_root / "danbooru/tag.sqlite"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"broken SQLite must stay for explicit repair")
    before = target.read_bytes()
    service = _initialize(root, target_root, monkeypatch)
    status = asyncio.run(service.ensure("zh-CN"))
    assert status["state"] == "error"
    assert status["installed"] is False
    assert status["error"]
    assert service.lookup(["blue_eyes"]) == {}
    assert target.read_bytes() == before
    assert service._auto_attempted is True


def test_invalid_bundled_seed_does_not_install_or_auto_download(project, tmp_path, monkeypatch):
    root, source = project
    (source / "metadata.json").write_text("{}", encoding="utf-8")
    target_root = tmp_path / "empty-user-data"
    service = _initialize(root, target_root, monkeypatch)
    assert asyncio.run(service.ensure("zh-CN"))["state"] == "error"
    assert not (target_root / "danbooru/tag.sqlite").exists()
    assert service.lookup(["blue_eyes"]) == {}

"""Pinned public assets, cold CLI, installation failures, and user-state boundaries."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import threading

import pytest

from mikazuki.tag_translation import dictionary_bundle as bundle

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/prefetch_tag_dictionary.py"


def _json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture(tmp_path):
    source = tmp_path / "source" / "danbooru"
    source.mkdir(parents=True)
    db = source / "tag.sqlite"
    with sqlite3.connect(db) as connection:
        connection.executescript("""
            CREATE TABLE tags(name TEXT PRIMARY KEY, category INTEGER, cn_name TEXT, post_count INTEGER);
            INSERT INTO tags VALUES ('blue_eyes', 0, '蓝瞳', 100);
            INSERT INTO tags VALUES ('long_hair', 0, '长发', 200);
        """)
    license_bytes = b"MIT License\nCopyright (c) synthetic fixture\n"
    (source / "LICENSE.ffdkj.txt").write_bytes(license_bytes)
    expected = {
        "version": 1,
        "source_url": "https://fixture.invalid/locked/tag.sqlite",
        "source_commit": "a" * 40,
        "git_blob_sha": bundle.git_blob_sha(db),
        "sha256": hashlib.sha256(db.read_bytes()).hexdigest(),
        "size_bytes": db.stat().st_size,
        "row_count": 2,
        "license": "MIT",
        "license_sha256": hashlib.sha256(license_bytes).hexdigest(),
        "license_file": str(source / "LICENSE.ffdkj.txt"),
    }
    _json(source / "source-manifest.json", {key: expected[key] for key in bundle.LOCK_FIELDS})
    _json(source / "metadata.json", {
        "installed_sha": expected["git_blob_sha"], "remote_sha": expected["git_blob_sha"],
        "download_url": expected["source_url"], "remote_size": expected["size_bytes"],
        "row_count": 2, "last_checked_at": "2026-10-13T00:00:00+00:00",
        "last_updated_at": "2026-10-13T00:00:00+00:00",
    })
    manifest = tmp_path / "release-lock.json"
    _json(manifest, expected)
    return source, expected, manifest


@contextmanager
def _http_payloads(payloads):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            value = payloads.get(self.path)
            if value is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(value)))
            self.end_headers()
            self.wfile.write(value)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()


def test_locked_bundle_verifies_without_mutating_files(tmp_path):
    source, expected, manifest = _fixture(tmp_path)
    before = {file.name: file.read_bytes() for file in source.iterdir()}
    result = bundle.verify_translation_assets(source.parent, manifest)
    assert result["installed"] and result["row_count"] == 2
    assert result["sha256"] == expected["sha256"]
    assert {file.name: file.read_bytes() for file in source.iterdir()} == before
    assert set(before) == set(bundle.BUNDLE_FILES)


@pytest.mark.parametrize("field", ["source_commit", "git_blob_sha", "sha256", "size_bytes", "row_count", "license_sha256"])
def test_artifact_cannot_self_report_a_different_release(tmp_path, field):
    source, expected, manifest = _fixture(tmp_path)
    artifact = json.loads((source / "source-manifest.json").read_text())
    artifact[field] = "b" * len(artifact[field]) if isinstance(artifact[field], str) else artifact[field] + 1
    _json(source / "source-manifest.json", artifact)
    with pytest.raises(bundle.DictionaryBundleError, match="release lock"):
        bundle.verify_bundle(source, manifest)


@pytest.mark.parametrize("extra", ["api_key", "configuration", "runtime_path"])
def test_metadata_cannot_carry_user_state(tmp_path, extra):
    source, expected, manifest = _fixture(tmp_path)
    metadata = json.loads((source / "metadata.json").read_text())
    metadata[extra] = "synthetic-user-state"
    _json(source / "metadata.json", metadata)
    with pytest.raises(bundle.DictionaryBundleError, match="seven public"):
        bundle.verify_bundle(source, manifest)


@pytest.mark.parametrize("relative", ["translation.json", "translations.sqlite3", "translations.sqlite3-wal", "models/file.bin", "danbooru/tag.sqlite-shm", "danbooru/temp/file.download"])
def test_strict_assets_reject_all_other_files_and_directories(tmp_path, relative):
    source, expected, manifest = _fixture(tmp_path)
    unexpected = source.parent / relative
    unexpected.parent.mkdir(parents=True, exist_ok=True)
    unexpected.write_bytes(b"synthetic-state-do-not-read")
    with pytest.raises(bundle.DictionaryBundleError):
        bundle.verify_translation_assets(source.parent, manifest)


@pytest.mark.parametrize("corrupt", ["truncate", "same_size", "license", "missing"])
def test_existing_corrupt_bundle_cannot_pass_if_missing(tmp_path, corrupt, monkeypatch):
    source, expected, manifest = _fixture(tmp_path)
    if corrupt == "truncate":
        (source / "tag.sqlite").write_bytes(b"")
    elif corrupt == "same_size":
        data = bytearray((source / "tag.sqlite").read_bytes())
        data[-1] ^= 1
        (source / "tag.sqlite").write_bytes(data)
    elif corrupt == "license":
        (source / "LICENSE.ffdkj.txt").write_bytes(b"wrong license")
    else:
        (source / "metadata.json").unlink()
    monkeypatch.setattr(bundle, "_download", lambda *_args: pytest.fail("Existing bad bundles require explicit repair"))
    with pytest.raises(bundle.DictionaryBundleError):
        bundle.prepare_bundle(source, if_missing=True, manifest=manifest)


@pytest.mark.parametrize("schema", ["missing_columns", "empty", "not_sqlite"])
def test_structural_database_validation_is_independent_of_hashes(tmp_path, schema):
    db = tmp_path / "bad.sqlite"
    if schema == "not_sqlite":
        db.write_bytes(b"not sqlite")
    else:
        with sqlite3.connect(db) as connection:
            connection.execute("CREATE TABLE tags(name TEXT)" if schema == "missing_columns" else
                               "CREATE TABLE tags(name TEXT, category INTEGER, cn_name TEXT, post_count INTEGER)")
    with pytest.raises(bundle.DictionaryBundleError):
        bundle.validate_database(db)


def test_download_candidates_share_release_hash_and_fallback_after_wrong_bytes(tmp_path):
    source, expected, manifest = _fixture(tmp_path)
    good = (source / "tag.sqlite").read_bytes()
    wrong = bytearray(good)
    wrong[-1] ^= 1
    with _http_payloads({"/bad": bytes(wrong), "/good": good}) as (base, requests):
        expected["source_url"] = base + "/good"
        expected["download_urls"] = [base + "/bad", base + "/good"]
        _json(manifest, expected)
        target = tmp_path / "output" / "danbooru"
        result = bundle.prepare_bundle(target, if_missing=True, manifest=manifest)
        assert result["downloaded"]
        assert requests == ["/bad", "/good"]
        assert bundle.verify_translation_assets(target.parent, manifest)["row_count"] == 2
        assert {entry.name for entry in target.parent.iterdir()} == {"danbooru"}


def test_network_or_hash_failure_retains_all_old_files(tmp_path):
    source, expected, manifest = _fixture(tmp_path)
    before = {file.name: file.read_bytes() for file in source.iterdir()}
    with _http_payloads({"/truncated": b"truncated"}) as (base, requests):
        expected["download_urls"] = [base + "/missing", base + "/truncated"]
        _json(manifest, expected)
        with pytest.raises(bundle.DictionaryBundleError, match="download failed"):
            bundle.prepare_bundle(source, force=True, manifest=manifest)
    assert {file.name: file.read_bytes() for file in source.iterdir()} == before
    assert {entry.name for entry in source.parent.iterdir()} == {"danbooru"}


@pytest.mark.parametrize("had_previous", [False, True])
def test_partial_install_failure_compensates_every_public_file(tmp_path, monkeypatch, had_previous):
    source, expected, manifest = _fixture(tmp_path)
    target = tmp_path / "target" / "danbooru"
    if had_previous:
        shutil.copytree(source, target)
    else:
        target.mkdir(parents=True)
    before = {file.name: file.read_bytes() for file in target.iterdir()}
    original_replace = bundle.os.replace

    def fail_once_during_publish(source_file, target_file):
        # Fail after new metadata is published for existing bundles, so losing
        # compensation would leave visibly different timestamps and fail.
        fault_file = "tag.sqlite" if had_previous else "metadata.json"
        if Path(source_file).name == fault_file and Path(source_file).parent.name != "backup":
            raise OSError("synthetic installation fault")
        return original_replace(source_file, target_file)

    monkeypatch.setattr(bundle.os, "replace", fail_once_during_publish)
    if had_previous:
        # Force prepares a fresh replacement and then fails midway through publishing.
        monkeypatch.setattr(bundle, "_download", lambda _url, path, _size: shutil.copyfile(source / "tag.sqlite", path))
        with pytest.raises(OSError, match="synthetic"):
            bundle.prepare_bundle(target, force=True, manifest=manifest)
    else:
        with pytest.raises(OSError, match="synthetic"):
            bundle.seed_bundle(source, target, manifest)
    assert {file.name: file.read_bytes() for file in target.iterdir()} == before
    assert {entry.name for entry in target.parent.iterdir()} == {"danbooru"}


def test_seed_preserves_existing_database_without_opening_it_or_the_source(tmp_path, monkeypatch):
    target = tmp_path / "user-state" / "danbooru"
    target.mkdir(parents=True)
    (target / "tag.sqlite").write_bytes(b"user-version-even-if-corrupt")
    (target / "metadata.json").write_bytes(b"user-metadata")
    (target.parent / "translation.json").write_bytes(b"synthetic-config")
    (target.parent / "translations.sqlite3").write_bytes(b"synthetic-cache")
    before = {str(path.relative_to(target.parent)): path.read_bytes() for path in target.parent.rglob("*") if path.is_file()}
    monkeypatch.setattr(bundle, "verify_bundle", lambda *_args: pytest.fail("No existing user database may be inspected"))
    result = bundle.seed_bundle(tmp_path / "missing-source", target)
    assert result["preserved"] and not result["seeded"]
    assert {str(path.relative_to(target.parent)): path.read_bytes() for path in target.parent.rglob("*") if path.is_file()} == before


def test_two_threads_seed_only_once_and_publish_database_last(tmp_path, monkeypatch):
    source, expected, manifest = _fixture(tmp_path)
    target = tmp_path / "user" / "danbooru"
    barrier = threading.Barrier(2)
    original_verify = bundle.verify_bundle
    published = []
    original_replace = bundle.os.replace

    def synchronize_source(directory, manifest=None):
        result = original_verify(directory, manifest)
        if Path(directory) == source:
            barrier.wait(timeout=5)
        return result

    def observe_replace(src, dst):
        if Path(dst).parent == target:
            published.append(Path(dst).name)
        return original_replace(src, dst)

    monkeypatch.setattr(bundle, "verify_bundle", synchronize_source)
    monkeypatch.setattr(bundle.os, "replace", observe_replace)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: bundle.seed_bundle(source, target, manifest), range(2)))
    assert sum(item["seeded"] for item in results) == 1
    assert published == list(bundle.BUNDLE_FILES)
    assert published[-1] == "tag.sqlite"
    assert original_verify(target, manifest)["installed"]


def test_two_processes_seed_only_once_with_zero_site_packages(tmp_path):
    source, expected, manifest = _fixture(tmp_path)
    target = tmp_path / "user" / "danbooru"
    code = ("import json,sys; from mikazuki.tag_translation.dictionary_bundle import seed_bundle; "
            "print(json.dumps(seed_bundle(sys.argv[1],sys.argv[2],sys.argv[3])))")
    command = [sys.executable, "-S", "-c", code, str(source), str(target), str(manifest)]
    processes = [subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    reports = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stderr
        reports.append(json.loads(stdout))
    assert sum(report["seeded"] for report in reports) == 1
    assert bundle.verify_bundle(target, manifest)["installed"]
    assert {entry.name for entry in target.parent.iterdir()} == {"danbooru"}


def test_real_cli_download_and_reuse_with_no_site_packages_and_no_runtime_side_effects(tmp_path):
    source, expected, manifest = _fixture(tmp_path)
    target = tmp_path / "package" / "danbooru"
    user_root = tmp_path / "runtime-must-stay-absent"
    env = {**os.environ, "MIKAZUKI_TAG_TRANSLATION_ROOT": str(user_root), "PYTHONPATH": ""}
    with _http_payloads({"/tag.sqlite": (source / "tag.sqlite").read_bytes()}) as (base, requests):
        expected["source_url"] = base + "/tag.sqlite"
        _json(manifest, expected)
        command = [sys.executable, "-S", str(CLI), "--directory", str(target), "--if-missing", "--strict", "--manifest", str(manifest)]
        for _ in range(2):
            completed = subprocess.run(command, env=env, cwd=tmp_path, capture_output=True, text=True, timeout=20)
            assert completed.returncode == 0, completed.stderr
        assert requests == ["/tag.sqlite"]
        assert not user_root.exists()
        command[command.index("--if-missing")] = "--verify-only"
        completed = subprocess.run(command, env=env, cwd=tmp_path, capture_output=True, text=True, timeout=20)
        assert completed.returncode == 0, completed.stderr
        assert requests == ["/tag.sqlite"]
    assert {entry.name for entry in target.parent.iterdir()} == {"danbooru"}


def test_release_manifest_and_license_are_fixed_public_assets():
    expected = bundle.load_manifest()
    assert expected["source_commit"] == "623a41c0ba1ea8b7be0ccf7cc925b15f8ec77222"
    assert expected["size_bytes"] == 24678400 and expected["row_count"] == 332385
    assert expected["sha256"] == "876ee9885218a7c1dbf7c879ef7b3339024eb47b3f9e8b98fbb77af16897a2bb"
    assert hashlib.sha256((ROOT / expected["license_file"]).read_bytes()).hexdigest() == expected["license_sha256"]
    assert all(expected["source_commit"] in url for url in expected["download_urls"])


def test_pinned_license_checkout_uses_lf_even_with_windows_autocrlf():
    completed = subprocess.run(["git", "-c", "core.autocrlf=true", "check-attr", "text", "eol", "--",
                                "docs/third_party/ffdkj-danbooru-tag-table-MIT.txt"],
                               cwd=ROOT, capture_output=True, text=True, timeout=10)
    assert completed.returncode == 0, completed.stderr
    assert ": text: set" in completed.stdout
    assert ": eol: lf" in completed.stdout


@pytest.mark.parametrize("newer", [False, True])
def test_non_strict_installer_preserves_valid_legacy_or_updated_user_library(tmp_path, newer):
    source, expected, manifest = _fixture(tmp_path)
    user = tmp_path / "user" / "danbooru"
    user.mkdir(parents=True)
    shutil.copyfile(source / "tag.sqlite", user / "tag.sqlite")
    (user / "metadata.json").write_bytes(b"legacy-public-metadata")
    (user.parent / "translations.sqlite3").write_bytes(b"synthetic-cache")
    (user.parent / "translation.json").write_bytes(b"synthetic-config")
    if newer:
        with sqlite3.connect(user / "tag.sqlite") as connection:
            connection.execute("INSERT INTO tags VALUES ('new_tag', 0, '新标签', 1)")
    before = {str(path.relative_to(user.parent)): path.read_bytes() for path in user.parent.rglob("*") if path.is_file()}
    completed = subprocess.run([sys.executable, "-S", str(CLI), "--directory", str(user), "--if-missing"],
                               cwd=tmp_path, capture_output=True, text=True, timeout=20)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)["dictionary"]
    assert result["preserved"] and result["row_count"] == (3 if newer else 2)
    assert {str(path.relative_to(user.parent)): path.read_bytes() for path in user.parent.rglob("*") if path.is_file()} == before
    # Installer compatibility does not relax the strict release or verify-only gate.
    for flags in (["--if-missing", "--strict"], ["--verify-only"]):
        completed = subprocess.run([sys.executable, "-S", str(CLI), "--directory", str(user), *flags],
                                   cwd=tmp_path, capture_output=True, text=True, timeout=20)
        assert completed.returncode != 0


def test_non_strict_installer_rejects_corrupt_existing_database_without_network(tmp_path):
    user = tmp_path / "user" / "danbooru"
    user.mkdir(parents=True)
    (user / "tag.sqlite").write_bytes(b"broken")
    completed = subprocess.run([sys.executable, "-S", str(CLI), "--directory", str(user), "--if-missing"],
                               cwd=tmp_path, capture_output=True, text=True, timeout=20)
    assert completed.returncode == 1
    assert (user / "tag.sqlite").read_bytes() == b"broken"
    assert {path.name for path in user.iterdir()} == {"tag.sqlite"}


def test_invalid_runtime_library_returns_missing_results_and_check_does_not_restore_ready(tmp_path, monkeypatch):
    import asyncio
    from mikazuki.tag_translation.chinese_dictionary_service import ChineseDictionaryService
    directory = tmp_path / "bad-runtime"
    directory.mkdir()
    (directory / "tag.sqlite").write_bytes(b"broken")
    service = ChineseDictionaryService(str(directory))
    service._invalid_database = True
    service._runtime.update(state="error", error="Corrupt dictionary")

    async def metadata():
        return {"sha": "a" * 40, "download_url": "https://fixture.invalid/tag.sqlite", "size": 100}

    monkeypatch.setattr(service, "_fetch_remote_metadata", metadata)
    assert service.lookup(["blue_eyes"]) == {}
    assert service.search("蓝") == []
    status = asyncio.run(service.check_update())
    assert status["state"] == "error" and not status["installed"]
    assert service._invalid_database


def test_successful_verified_runtime_replacement_clears_invalid_flag(tmp_path, monkeypatch):
    import asyncio
    from mikazuki.tag_translation.chinese_dictionary_service import ChineseDictionaryService
    source, expected, manifest = _fixture(tmp_path)
    target = tmp_path / "runtime"
    target.mkdir()
    (target / "tag.sqlite").write_bytes(b"broken")
    # Even a metadata SHA matching upstream must not trigger the no-op shortcut for a corrupt DB.
    _json(target / "metadata.json", {"installed_sha": expected["git_blob_sha"]})
    service = ChineseDictionaryService(str(target))
    service._invalid_database = True
    calls = []

    async def metadata():
        return {"sha": expected["git_blob_sha"], "download_url": expected["source_url"], "size": expected["size_bytes"]}

    async def download(_url, path):
        calls.append("download")
        shutil.copyfile(source / "tag.sqlite", path)

    monkeypatch.setattr(service, "_fetch_remote_metadata", metadata)
    monkeypatch.setattr(service, "_download_file", download)
    asyncio.run(service._download_and_install())
    assert calls == ["download"]
    assert not service._invalid_database
    assert service.status()["state"] == "ready" and service.status()["installed"]
    assert service.lookup(["blue_eyes"])["blue_eyes"]["text"] == "蓝瞳"


@pytest.mark.parametrize("cancel", [False, True])
def test_failed_or_cancelled_runtime_repair_keeps_invalid_flag_and_old_bytes(tmp_path, monkeypatch, cancel):
    import asyncio
    from mikazuki.tag_translation.chinese_dictionary_service import ChineseDictionaryService
    target = tmp_path / "bad-runtime"
    target.mkdir()
    (target / "tag.sqlite").write_bytes(b"original-corrupt-bytes")
    service = ChineseDictionaryService(str(target))
    service._invalid_database = True

    async def metadata():
        return {"sha": "a" * 40, "download_url": "https://fixture.invalid/tag.sqlite", "size": 100}

    async def download(_url, path):
        Path(path).write_bytes(b"partial-download")
        if cancel:
            raise asyncio.CancelledError()
        raise OSError("synthetic download failure")

    monkeypatch.setattr(service, "_fetch_remote_metadata", metadata)
    monkeypatch.setattr(service, "_download_file", download)
    if cancel:
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(service._download_and_install())
    else:
        asyncio.run(service._download_and_install())
    assert service._invalid_database and not service.status()["installed"]
    assert service.status()["state"] == ("cancelled" if cancel else "error")
    assert (target / "tag.sqlite").read_bytes() == b"original-corrupt-bytes"
    assert list(target.iterdir()) == [target / "tag.sqlite"]

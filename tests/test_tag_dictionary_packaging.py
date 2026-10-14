"""Execute Windows packaging gates and Release copy policy on isolated fixtures."""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")
WINDOWS_TOOLS = POWERSHELL and shutil.which("robocopy")
PUBLIC_FILES = {"tag.sqlite", "metadata.json", "source-manifest.json", "LICENSE.ffdkj.txt"}


def _quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _powershell(code: str, temp: Path) -> subprocess.CompletedProcess:
    runner = temp / "test-runner.ps1"
    runner.write_text('$ErrorActionPreference="Stop"\n' + code, encoding="utf-8-sig")
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(runner)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=45,
    )


def _stage_code(trainer: Path) -> None:
    for relative in (
        "scripts/prefetch_tag_dictionary.py",
        "scripts/portable/seed_tag_dictionary.py",
        "mikazuki/__init__.py",
        "mikazuki/tag_translation/__init__.py",
        "mikazuki/tag_translation/dictionary_bundle.py",
        "docs/third_party/ffdkj-danbooru-tag-table-MIT.txt",
    ):
        destination = trainer / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)


def _public_bundle(trainer: Path) -> tuple[Path, Path]:
    _stage_code(trainer)
    directory = trainer / "assets/tag_translation/danbooru"
    directory.mkdir(parents=True)
    database = directory / "tag.sqlite"
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("CREATE TABLE tags (name TEXT, category INTEGER, cn_name TEXT, post_count INTEGER)")
        connection.executemany("INSERT INTO tags VALUES (?, ?, ?, ?)", [("cat", 0, "猫", 5), ("blue_eyes", 0, "蓝眼睛", 10)])
    payload = database.read_bytes()
    source = json.loads((ROOT / "scripts/assets/tag-dictionary-manifest.json").read_text(encoding="utf-8"))
    source.update(
        size_bytes=len(payload),
        row_count=2,
        sha256=hashlib.sha256(payload).hexdigest(),
        git_blob_sha=hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest(),
    )
    manifest = trainer / "scripts/assets/tag-dictionary-manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(source), encoding="utf-8")
    public_fields = {"version", "source_url", "source_commit", "git_blob_sha", "sha256", "size_bytes", "row_count", "license", "license_sha256", "license_source_url"}
    (directory / "source-manifest.json").write_text(json.dumps({key: value for key, value in source.items() if key in public_fields}), encoding="utf-8")
    shutil.copyfile(trainer / source["license_file"], directory / "LICENSE.ffdkj.txt")
    metadata = {
        "installed_sha": source["git_blob_sha"],
        "remote_sha": source["git_blob_sha"],
        "download_url": source["source_url"],
        "remote_size": len(payload),
        "row_count": 2,
        "last_checked_at": "2026-10-13T00:00:00+00:00",
        "last_updated_at": "2026-10-13T00:00:00+00:00",
    }
    (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return directory, manifest


def _gate(trainer: Path, mode: str, temp: Path) -> subprocess.CompletedProcess:
    return _powershell(
        f". {_quote(ROOT / 'build-scripts/tag-dictionary-bundle.ps1')}\n"
        f"Invoke-PortableTagDictionary -PythonExe {_quote(sys.executable)} "
        f"-TrainerDir {_quote(trainer)} -Mode {mode}\n",
        temp,
    )


@pytest.mark.skipif(not POWERSHELL, reason="Windows packaging requires PowerShell")
def test_shared_prepare_and_archive_gate_uses_only_public_assets_without_site_packages(tmp_path: Path):
    trainer = tmp_path / "Next-Trainer"
    directory, _ = _public_bundle(trainer)
    sentinel = tmp_path / "python_embeded/Lib/site-packages/keep-me.txt"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_bytes(b"installed-runtime-must-survive")
    before = {path.name: path.read_bytes() for path in directory.iterdir()}

    for mode in ("Prepare", "Verify"):
        result = _gate(trainer, mode, tmp_path)
        assert result.returncode == 0, result.stderr + result.stdout
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == before
    assert set(before) == PUBLIC_FILES
    assert sentinel.read_bytes() == b"installed-runtime-must-survive"


@pytest.mark.skipif(not POWERSHELL, reason="Windows packaging requires PowerShell")
@pytest.mark.parametrize("mode,problem", [
    ("Verify", problem) for problem in ("missing", "bad-hash", "bad-metadata", "cache", "settings", "model")
] + [("Prepare", problem) for problem in ("bad-hash", "bad-metadata", "cache", "settings", "model")])
def test_archive_gate_rejects_invalid_or_polluted_dictionary_bundle(tmp_path: Path, mode: str, problem: str):
    trainer = tmp_path / "Next-Trainer"
    directory, _ = _public_bundle(trainer)
    if problem == "missing":
        (directory / "tag.sqlite").unlink()
    elif problem == "bad-hash":
        with closing(sqlite3.connect(directory / "tag.sqlite")) as connection, connection:
            connection.execute("UPDATE tags SET cn_name='changed' WHERE name='cat'")
    elif problem == "bad-metadata":
        (directory / "metadata.json").write_text("{}", encoding="utf-8")
    else:
        paths = {"cache": "translations.sqlite3", "settings": "translation.json", "model": "models/private/weights.gguf"}
        illegal = directory.parent / paths[problem]
        illegal.parent.mkdir(parents=True, exist_ok=True)
        illegal.write_bytes(b"private-sentinel")
    result = _gate(trainer, mode, tmp_path)
    assert result.returncode != 0
    assert "no release archive may be produced" in result.stderr + result.stdout
    if problem in {"cache", "settings", "model"}:
        assert illegal.read_bytes() == b"private-sentinel"


@pytest.mark.skipif(not WINDOWS_TOOLS, reason="Actual Release copy requires Windows robocopy")
def test_old_copy_policy_excludes_only_the_absolute_translation_runtime_tree(tmp_path: Path):
    project = tmp_path / "project"
    target = tmp_path / "target"
    private = project / "assets/tag_translation/translation.json"
    private.parent.mkdir(parents=True)
    private.write_bytes(b"private-setting")
    source_module = project / "mikazuki/tag_translation/public-code.py"
    source_module.parent.mkdir(parents=True)
    source_module.write_bytes(b"public source")
    source = (ROOT / "build-scripts/03-copy-project.ps1").read_text(encoding="utf-8-sig")
    function = source.split("function Get-CorePortableCopyPolicy", 1)[1].split("$copyPolicy =", 1)[0]
    result = _powershell(
        f"$ProjectRoot={_quote(project)}\nfunction Get-CorePortableCopyPolicy{function}\n"
        f"$excludeArgs=(Get-CorePortableCopyPolicy).excludedDirectories | ForEach-Object {{ '/XD', $_ }}\n"
        f"& robocopy {_quote(project)} {_quote(target)} /E /NFL /NDL /NJH /NJS @excludeArgs | Out-Null\n"
        "if ($LASTEXITCODE -ge 8) { throw 'copy failed' }\n",
        tmp_path,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert not (target / "assets/tag_translation").exists()
    assert (target / "mikazuki/tag_translation/public-code.py").read_bytes() == b"public source"


def _release_merge(staging: Path, trainer: Path, temp: Path) -> subprocess.CompletedProcess:
    source = (ROOT / "scripts/portable/update_from_release.ps1").read_text(encoding="utf-8-sig")
    block = source.split("# Validate a new-format Release", 1)[1].split("$stagingGit =", 1)[0]
    portable = trainer.parent
    python = portable / "python_embeded/python.exe"
    python.parent.mkdir(parents=True, exist_ok=True)
    # A launcher script avoids relocating the venv interpreter and its stdlib.
    # Override this one package interpreter for the isolated updater code block.
    block = block.replace('Join-Path $PortableRoot "python_embeded\\python.exe"', _quote(sys.executable))
    return _powershell(
        f"$stagingTrainer={_quote(staging)}\n$TrainerDir={_quote(trainer)}\n$PortableRoot={_quote(portable)}\n"
        "function Write-Step([string]$Message) { Write-Output $Message }\n"
        "# Validate a new-format Release" + block,
        temp,
    )


@pytest.mark.skipif(not WINDOWS_TOOLS, reason="Actual Release copy requires Windows robocopy")
@pytest.mark.parametrize("existing_dictionary", [False, True])
def test_release_update_preserves_all_runtime_data_and_only_seeds_missing_dictionary(tmp_path: Path, existing_dictionary: bool):
    staging = tmp_path / "stage/Next-Trainer"
    directory, _ = _public_bundle(staging)
    (staging / "version-marker.txt").write_bytes(b"new public code")
    trainer = tmp_path / "installed/Next-Trainer"
    runtime = trainer / "assets/tag_translation"
    private_paths = ["translation.json", "translations.sqlite3", "llm.json", "models/local/weights.gguf", "runtime/server.exe"]
    for relative in private_paths:
        path = runtime / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"user:{relative}".encode())
    if existing_dictionary:
        (runtime / "danbooru").mkdir()
        # Deliberately unreadable as SQLite: an update must preserve it too,
        # leaving diagnosis/replacement to the explicit dictionary maintenance UI.
        (runtime / "danbooru/tag.sqlite").write_bytes(b"user-newer-dictionary")
        (runtime / "danbooru/metadata.json").write_bytes(b"user-metadata")
    before = {path.relative_to(runtime): path.read_bytes() for path in runtime.rglob("*") if path.is_file()}
    result = _release_merge(staging, trainer, tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (trainer / "version-marker.txt").read_bytes() == b"new public code"
    for relative, data in before.items():
        assert (runtime / relative).read_bytes() == data, relative
    if existing_dictionary:
        assert not (runtime / "danbooru/source-manifest.json").exists()
    else:
        assert {path.name for path in (runtime / "danbooru").iterdir()} == PUBLIC_FILES
        for name in PUBLIC_FILES:
            assert (runtime / "danbooru" / name).read_bytes() == (directory / name).read_bytes()


@pytest.mark.skipif(not WINDOWS_TOOLS, reason="Actual Release copy requires Windows robocopy")
@pytest.mark.parametrize("damage", ["bad-database", "missing-seeder", "missing-lock", "private-cache"])
def test_invalid_new_release_is_rejected_before_overwriting_project(tmp_path: Path, damage: str):
    staging = tmp_path / "stage/Next-Trainer"
    directory, _ = _public_bundle(staging)
    (staging / "version-marker.txt").write_bytes(b"would-overwrite")
    if damage == "bad-database":
        (directory / "tag.sqlite").write_bytes(b"broken")
    elif damage == "missing-seeder":
        (staging / "scripts/portable/seed_tag_dictionary.py").unlink()
    elif damage == "missing-lock":
        (staging / "scripts/assets/tag-dictionary-manifest.json").unlink()
    else:
        (directory.parent / "translations.sqlite3").write_bytes(b"unwanted-cache")
    trainer = tmp_path / "installed/Next-Trainer"
    trainer.mkdir(parents=True)
    (trainer / "version-marker.txt").write_bytes(b"existing-project")
    existing = trainer / "assets/tag_translation/danbooru/tag.sqlite"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"existing-user-dictionary")
    result = _release_merge(staging, trainer, tmp_path)
    assert result.returncode != 0
    assert (trainer / "version-marker.txt").read_bytes() == b"existing-project"
    assert existing.read_bytes() == b"existing-user-dictionary"


@pytest.mark.skipif(not WINDOWS_TOOLS, reason="Actual Release copy requires Windows robocopy")
def test_legacy_release_cannot_overwrite_translation_data_even_if_its_archive_contains_cache(tmp_path: Path):
    staging = tmp_path / "stage/Next-Trainer"
    trainer = tmp_path / "installed/Next-Trainer"
    for relative in ("translation.json", "translations.sqlite3", "danbooru/tag.sqlite", "models/local/weights.gguf"):
        for owner, prefix in ((staging, b"legacy-package:"), (trainer, b"installed-user:")):
            path = owner / "assets/tag_translation" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(prefix + relative.encode())
    (staging / "version-marker.txt").write_bytes(b"legacy-public-code")
    result = _release_merge(staging, trainer, tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (trainer / "version-marker.txt").read_bytes() == b"legacy-public-code"
    for relative in ("translation.json", "translations.sqlite3", "danbooru/tag.sqlite", "models/local/weights.gguf"):
        assert (trainer / "assets/tag_translation" / relative).read_bytes() == b"installed-user:" + relative.encode()


def test_every_supported_archive_entry_has_the_same_final_dictionary_gate():
    for name in (
        "build_portable.ps1", "build_portable_2026_full.ps1", "build_portable_kohya_only.ps1",
        "build_portable_musubi_only.ps1", "resume_portable_2026_full.ps1", "build-all.ps1", "05-create-zip.ps1",
    ):
        source = (ROOT / "build-scripts" / name).read_text(encoding="utf-8-sig")
        assert 'tag-dictionary-bundle.ps1' in source, name
        assert '-Mode Verify' in source, name
    for name in ("build_portable.ps1", "build_portable_musubi_only.ps1", "resume_portable_2026_full.ps1", "build-all.ps1"):
        assert '-Mode Prepare' in (ROOT / "build-scripts" / name).read_text(encoding="utf-8-sig"), name

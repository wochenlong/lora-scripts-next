import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from mikazuki.user_data import (
    RevisionConflict,
    UserDataError,
    UserDataStore,
)


def test_defaults_do_not_depend_on_cwd_or_create_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = UserDataStore()
    assert store.root == Path(__file__).resolve().parents[1] / "user_data"
    fresh = UserDataStore(tmp_path / "new")
    assert fresh.read_settings() == {"schema_version": 1, "revision": 0}
    assert not fresh.root.exists()


def test_patch_preserves_nested_values_and_rejects_stale_revision(tmp_path):
    store = UserDataStore(tmp_path)
    first = store.patch_settings({"startup": {"gui": {"port": 6006, "host": "0.0.0.0"}}}, 0)
    assert first["revision"] == 1
    second = store.patch_settings({"startup": {"gui": {"port": 28001}}}, 1)
    assert second["startup"]["gui"] == {"port": 28001, "host": "0.0.0.0"}
    assert json.loads((tmp_path / "settings.json.bak").read_text()) == first
    with pytest.raises(RevisionConflict):
        store.patch_settings({"startup": {"gui": {"port": 9999}}}, 1)
    assert store.read_settings() == second


def test_tasks_auto_retry_max_patch_roundtrip(tmp_path):
    store = UserDataStore(tmp_path)
    updated = store.patch_settings({"tasks": {"auto_retry_max": 2}}, 0)
    assert updated["tasks"] == {"auto_retry_max": 2}
    assert UserDataStore(tmp_path).read_settings()["tasks"]["auto_retry_max"] == 2


def test_paths_and_defaults_are_preserved_across_instances(tmp_path):
    original = UserDataStore(tmp_path)
    expected = original.patch_settings({
        "paths": {"tagger_models": {"wd-eva02": "D:/models/wd"}, "models": {"anima": "./models/anima"}},
        "engine_prefs": {"defaultEngine": "ai-toolkit", "rememberLast": False},
    }, 0)
    assert UserDataStore(tmp_path).read_settings() == expected


@pytest.mark.parametrize("patch", [
    {"schema_version": 1},
    {"revision": 9},
    {"unknown": True},
    {"startup": {"gui": {"port": True}}},
    {"startup": {"gui": {"port": 65536}}},
    {"startup": {"gui": {"port_conflict": "disable"}}},
    {"startup": {"monitor": {"mode": "public"}}},
    {"startup": {"gui": {"host": ""}}},
    {"engine_prefs": {"defaultEngine": "missing"}},
    {"engine_prefs": {"defaultEngine": []}},
    {"engine_prefs": {"lastByModel": {"anima": {"engine": [], "target": "lora"}}}},
    {"startup": {"gui": {"port_conflict": []}}},
    {"paths": {"tagger_models": {"wd": 123}}},
    {"api": {"provider": {"api_key": "do-not-store"}}},
    {"tasks": {"auto_retry_max": 10}},
    {"tasks": {"auto_retry_max": "2"}},
    {"tasks": {"auto_retry_max": -1}},
    {"tasks": {"unknown": 1}},
])
def test_invalid_patch_never_creates_settings(tmp_path, patch):
    store = UserDataStore(tmp_path)
    with pytest.raises(UserDataError):
        store.patch_settings(patch, 0)
    assert not (tmp_path / "settings.json").exists()


def test_corrupt_file_is_not_overwritten(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{broken", encoding="utf-8")
    store = UserDataStore(tmp_path)
    with pytest.raises(UserDataError):
        store.read_settings()
    with pytest.raises(UserDataError):
        store.patch_settings({"engine_prefs": {"rememberLast": False}}, 0)
    assert path.read_text() == "{broken"


def test_handwritten_startup_settings_accept_omitted_version(tmp_path):
    (tmp_path / "settings.json").write_text('{"startup":{"gui":{"port":6006}}}')
    settings = UserDataStore(tmp_path).read_settings()
    assert settings["revision"] == 0
    assert settings["startup"]["gui"]["port"] == 6006


def test_failed_replace_preserves_settings(tmp_path, monkeypatch):
    store = UserDataStore(tmp_path)
    first = store.patch_settings({"engine_prefs": {"rememberLast": False}}, 0)
    original = store.patch_settings({"engine_prefs": {"rememberLast": True}}, 1)
    import mikazuki.user_data as module
    real_replace = module.os.replace

    def fail_settings(source, destination):
        if Path(destination).name == "settings.json":
            raise OSError("disk unavailable")
        return real_replace(source, destination)

    monkeypatch.setattr(module.os, "replace", fail_settings)
    with pytest.raises(UserDataError):
        store.patch_settings({"engine_prefs": {"rememberLast": False}}, 2)
    assert store.read_settings() == original
    assert json.loads((tmp_path / "settings.json.bak").read_text()) == first


def test_only_one_concurrent_writer_wins(tmp_path):
    def update(port):
        try:
            UserDataStore(tmp_path).patch_settings({"startup": {"gui": {"port": port}}}, 0)
            return "saved"
        except RevisionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(update, [28001, 28002])) == ["conflict", "saved"]


def test_credentials_are_separate_and_metadata_does_not_leak(tmp_path):
    store = UserDataStore(tmp_path)
    store.set_credential("huggingface", "hf-test-sensitive", 0)
    assert store.credential_metadata() == {"schema_version": 1, "revision": 1,
                                           "providers": {"huggingface": {"configured": True}}}
    assert "hf-test-sensitive" not in json.dumps(store.credential_metadata())
    assert store.read_settings() == {"schema_version": 1, "revision": 0}
    assert store.get_credential("huggingface") == "hf-test-sensitive"
    with pytest.raises(RevisionConflict):
        store.set_credential("huggingface", "replacement", 0)
    store.set_credential("huggingface", None, 1)
    assert store.get_credential("huggingface") is None


def test_symlink_settings_outside_root_is_rejected(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    root = tmp_path / "user_data"
    root.mkdir()
    try:
        (root / "settings.json").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(UserDataError):
        UserDataStore(root).read_settings()


def test_configured_model_paths_resolve_against_project_root(tmp_path, monkeypatch):
    store = UserDataStore(tmp_path / "project" / "user_data")
    store.patch_settings({"paths": {"tagger_models": {"wd": "./models/wd"}}}, 0)
    monkeypatch.chdir(tmp_path)
    assert store.model_path("tagger_models", "wd") == tmp_path / "project" / "models" / "wd"
    assert store.model_path("tagger_models", "absent") is None


def test_auth_limit_rejected_before_write(tmp_path):
    data = {"schema_version": 1, "revision": 1,
            "providers": {f"p{i}": "secret" for i in range(1000)}}
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(data))
    store = UserDataStore(tmp_path)
    with pytest.raises(UserDataError):
        store.set_credential("one-too-many", "secret", 1)
    assert json.loads(path.read_text()) == data
    assert store.get_credential("p0") == "secret"


def test_separate_process_writers_use_revision_lock(tmp_path):
    script = """
import sys
from mikazuki.user_data import UserDataStore, RevisionConflict
try:
    UserDataStore(sys.argv[1]).patch_settings({"startup":{"gui":{"port":28001}}}, 0)
    print("saved")
except RevisionConflict:
    print("conflict")
"""
    workers = [subprocess.Popen([sys.executable, "-c", script, str(tmp_path)],
                                cwd=Path(__file__).resolve().parents[1],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
               for _ in range(2)]
    results = []
    for process in workers:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stderr
        results.append(stdout.strip())
    assert sorted(results) == ["conflict", "saved"]


def test_failed_backup_rotation_rolls_back_primary(tmp_path, monkeypatch):
    store = UserDataStore(tmp_path)
    first = store.patch_settings({"engine_prefs": {"rememberLast": False}}, 0)
    second = store.patch_settings({"engine_prefs": {"rememberLast": True}}, 1)
    import mikazuki.user_data as module
    real_replace = module.os.replace

    def fail_backup(source, destination):
        if Path(destination).name.endswith(".bak"):
            raise OSError("backup blocked")
        return real_replace(source, destination)

    monkeypatch.setattr(module.os, "replace", fail_backup)
    with pytest.raises(UserDataError):
        store.patch_settings({"engine_prefs": {"rememberLast": False}}, 2)
    assert store.read_settings() == second
    assert json.loads((tmp_path / "settings.json.bak").read_text()) == first


@pytest.mark.parametrize("fail_backup", [False, True])
def test_no_allocation_needed_after_primary_publication(tmp_path, monkeypatch, fail_backup):
    import mikazuki.user_data as module

    store = UserDataStore(tmp_path)
    first = store.patch_settings({"paths": {"datasets": "first"}}, 0)
    second = store.patch_settings({"paths": {"datasets": "second"}}, 1)
    real_replace = module.os.replace
    real_mkstemp = module.tempfile.mkstemp
    published = False
    allocations_after_publish = []

    def allocate(*args, **kwargs):
        if published:
            allocations_after_publish.append(kwargs)
            raise OSError("disk full after publication")
        return real_mkstemp(*args, **kwargs)

    def replace(source, destination):
        nonlocal published
        if Path(destination).name == "settings.json.bak" and fail_backup:
            raise OSError("backup blocked")
        real_replace(source, destination)
        if Path(destination).name == "settings.json":
            published = True

    monkeypatch.setattr(module.tempfile, "mkstemp", allocate)
    monkeypatch.setattr(module.os, "replace", replace)
    if fail_backup:
        with pytest.raises(UserDataError):
            store.patch_settings({"paths": {"datasets": "third"}}, 2)
        assert store.read_settings() == second
        assert json.loads((tmp_path / "settings.json.bak").read_text()) == first
    else:
        third = store.patch_settings({"paths": {"datasets": "third"}}, 2)
        assert store.read_settings() == third
        assert json.loads((tmp_path / "settings.json.bak").read_text()) == second
    assert published
    assert not allocations_after_publish
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        ".write.lock", "settings.json", "settings.json.bak",
    ]


def test_previous_primary_is_fsynced_before_publication(tmp_path, monkeypatch):
    import mikazuki.user_data as module

    store = UserDataStore(tmp_path)
    previous = store.patch_settings({"paths": {"datasets": "previous"}}, 0)
    real_mkstemp = module.tempfile.mkstemp
    real_fsync = module.os.fsync
    real_replace = module.os.replace
    allocated = {}
    synced = set()
    checked = False

    def allocate(*args, **kwargs):
        fd, name = real_mkstemp(*args, **kwargs)
        allocated[fd] = Path(name)
        return fd, name

    def fsync(fd):
        real_fsync(fd)
        synced.add(allocated[fd])

    def replace(source, destination):
        nonlocal checked
        if Path(destination).name == "settings.json":
            copies = [path for path in synced if path.exists()
                      and json.loads(path.read_text(encoding="utf-8")) == previous]
            assert copies, "Previous primary must be fsynced on disk before replacement"
            checked = True
        real_replace(source, destination)

    monkeypatch.setattr(module.tempfile, "mkstemp", allocate)
    monkeypatch.setattr(module.os, "fsync", fsync)
    monkeypatch.setattr(module.os, "replace", replace)
    store.patch_settings({"paths": {"datasets": "replacement"}}, 1)
    assert checked


def test_failed_backup_and_rollback_keep_durable_previous_primary(tmp_path, monkeypatch):
    import mikazuki.user_data as module

    store = UserDataStore(tmp_path)
    first = store.patch_settings({"paths": {"datasets": "first"}}, 0)
    second = store.patch_settings({"paths": {"datasets": "second"}}, 1)
    real_replace = module.os.replace
    published = False

    def replace(source, destination):
        nonlocal published
        if published:
            raise OSError("replacements unavailable after publication")
        real_replace(source, destination)
        if Path(destination).name == "settings.json":
            published = True

    monkeypatch.setattr(module.os, "replace", replace)
    with pytest.raises(UserDataError) as error:
        store.patch_settings({"paths": {"datasets": "third"}}, 2)
    assert store.read_settings()["revision"] == 3
    assert json.loads((tmp_path / "settings.json.bak").read_text()) == first
    recovery = [path for path in tmp_path.iterdir()
                if path.name not in {".write.lock", "settings.json", "settings.json.bak"}]
    assert len(recovery) == 1
    assert json.loads(recovery[0].read_text(encoding="utf-8")) == second
    assert recovery[0].name in str(error.value)


@pytest.mark.parametrize("name,raw", [
    ("settings.json", b"[" * 1200 + b"0" + b"]" * 1200),
    ("auth.json", b"[" * 1200 + b"0" + b"]" * 1200),
    ("settings.json", b'{"paths":{"datasets":"sensitive-value\\ud800"}}'),
    ("auth.json", b'{"providers":{"provider":"sensitive-value\\udfff"}}'),
    ("auth.json", b'{"schema_version":true,"providers":{"provider":"sensitive-value"}}'),
    ("auth.json", b'{"schema_version":1.0,"providers":{"provider":"sensitive-value"}}'),
])
def test_invalid_stored_json_blocks_reads_and_writes_without_data_loss(
    tmp_path, name, raw, bounded_recursion,
):
    path = tmp_path / name
    path.write_bytes(raw)
    store = UserDataStore(tmp_path)
    if name == "settings.json":
        read = store.read_settings
        write = lambda: store.patch_settings({}, 0)
    else:
        read = store.credential_metadata
        write = lambda: store.set_credential("provider", "replacement", 0)
    for operation in (read, write):
        with pytest.raises(UserDataError) as error:
            operation()
        assert "sensitive-value" not in str(error.value)
        assert path.read_bytes() == raw


@pytest.fixture
def bounded_recursion():
    previous = sys.getrecursionlimit()
    sys.setrecursionlimit(300)
    try:
        yield
    finally:
        sys.setrecursionlimit(previous)


def test_valid_unicode_surrogate_pair_round_trips(tmp_path):
    store = UserDataStore(tmp_path)
    value = json.loads('"\\ud83d\\ude00"')
    result = store.patch_settings({"paths": {"datasets": value}}, 0)
    assert store.read_settings() == result
    store.set_credential("provider", value, 0)
    assert store.get_credential("provider") == value

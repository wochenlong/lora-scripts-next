"""Profile persistence across source versions, with real task log/queue writes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mikazuki.paths import data_path


REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated_profile_environment(monkeypatch):
    for name in (
        "NEXT_TRAINER_DATA_ROOT", "NEXT_TRAINER_STATE_ROOT", "MIKAZUKI_TASK_QUEUE_FILE",
        "NEXT_TRAINER_NETWORK_CONFIG", "NEXT_TRAINER_DOWNLOAD_SOURCES_CONFIG",
    ):
        monkeypatch.delenv(name, raising=False)


def test_unconfigured_paths_keep_exact_legacy_behavior_and_do_not_create_files(tmp_path, monkeypatch):
    from mikazuki.download_sources import config_path as sources_path
    from mikazuki.networking.policy import config_path as network_path
    from mikazuki.tasks import Task, default_queue_path
    from mikazuki.user_data import UserDataStore

    monkeypatch.chdir(tmp_path)
    assert data_path("config/auto.toml") == Path("config/auto.toml")
    assert data_path("logs", legacy_base=tmp_path) == tmp_path / "logs"
    assert network_path() == Path("config/network.local.json")
    assert sources_path() == Path("config/download-sources.local.json")
    assert default_queue_path() == tmp_path / "logs/task_queue.json"
    assert UserDataStore().root == REPO / "user_data"
    task = Task("legacy-log", ["unused"], metadata={"log_file": "logs/keep-forward-slashes.log"})
    assert task.log_file == "logs/keep-forward-slashes.log"
    assert task.metadata["log_file"] == "logs/keep-forward-slashes.log"
    assert not list(tmp_path.iterdir())


def test_shared_preferences_and_per_version_state_have_distinct_roots(tmp_path, monkeypatch):
    profile, state = tmp_path / "用户 配置", tmp_path / "用户 配置/compat/main-v1"
    monkeypatch.setenv("NEXT_TRAINER_DATA_ROOT", str(profile))
    assert data_path("logs/tasks.log", state=True) == profile / "logs/tasks.log"
    monkeypatch.setenv("NEXT_TRAINER_STATE_ROOT", str(state))
    assert data_path("user_data") == profile / "user_data"
    assert data_path("logs/tasks.log", state=True) == state / "logs/tasks.log"
    assert not profile.exists()


def test_state_override_alone_does_not_redirect_shared_preferences(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXT_TRAINER_STATE_ROOT", str(tmp_path / "state"))
    assert data_path("config/network.local.json", state=True) == tmp_path / "state/config/network.local.json"
    assert data_path("user_data", legacy_base=REPO) == REPO / "user_data"


@pytest.mark.parametrize("name,state", [("NEXT_TRAINER_DATA_ROOT", False), ("NEXT_TRAINER_STATE_ROOT", True)])
def test_relative_profile_root_is_rejected_before_writing(tmp_path, monkeypatch, name, state):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(name, "relative-profile")
    with pytest.raises(ValueError, match=name):
        data_path("user_data", state=state)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("relative", ["../settings.json", "config/../../escape", Path.cwd() / "absolute"])
def test_application_path_cannot_escape_selected_root(tmp_path, monkeypatch, relative):
    monkeypatch.setenv("NEXT_TRAINER_DATA_ROOT", str(tmp_path / "profile"))
    with pytest.raises(ValueError, match="relative"):
        data_path(relative)
    assert not list(tmp_path.iterdir())


def test_existing_explicit_paths_keep_priority(tmp_path, monkeypatch):
    from mikazuki.download_sources import config_path as sources_path
    from mikazuki.networking.policy import config_path as network_path
    from mikazuki.tasks import Task, TaskManager, default_queue_path
    from mikazuki.user_data import UserDataStore

    monkeypatch.setenv("NEXT_TRAINER_DATA_ROOT", str(tmp_path / "profile"))
    monkeypatch.setenv("NEXT_TRAINER_STATE_ROOT", str(tmp_path / "profile/compat/v1"))
    monkeypatch.setenv("MIKAZUKI_TASK_QUEUE_FILE", "custom-queue.json")
    monkeypatch.setenv("NEXT_TRAINER_NETWORK_CONFIG", "custom-network.json")
    monkeypatch.setenv("NEXT_TRAINER_DOWNLOAD_SOURCES_CONFIG", "custom-sources.json")
    assert default_queue_path() == Path("custom-queue.json")
    assert network_path() == Path("custom-network.json")
    assert sources_path() == Path("custom-sources.json")
    assert UserDataStore(tmp_path / "explicit").root == tmp_path / "explicit"
    manager = TaskManager()
    manager.enable_persistence(tmp_path / "explicit-queue.json")
    assert manager._persist_path == tmp_path / "explicit-queue.json"
    task = Task("external-log", ["unused"], metadata={"log_file": str(tmp_path / "external.log")})
    assert task.log_file == str(tmp_path / "external.log")
    assert not (tmp_path / "profile").exists()


ROUNDTRIP = r'''
import json, os, sys, time
from pathlib import Path
from mikazuki.app.config import app_config
from mikazuki.download_sources import DownloadSources, save_download_sources
from mikazuki.networking.policy import config_path
from mikazuki.paths import data_path
from mikazuki.tasks import TaskManager, TaskStatus, default_queue_path
from mikazuki.update_check import _save_cache
from mikazuki.user_data import UserDataStore

label = sys.argv[1]
store = UserDataStore()
before = store.read_settings()
revision = before['revision']
store.patch_settings({'startup': {'gui': {'port': 28000 + revision}}}, revision)
app_config.load_config()
previous_label = app_config['profile_test_label']
app_config['profile_test_label'] = label
app_config.save_config()
network = config_path()
network.parent.mkdir(parents=True, exist_ok=True)
network.write_text('{"mode":"direct"}', encoding='utf-8')
save_download_sources(DownloadSources(hf_endpoint='https://example.invalid'))
_save_cache({'ts': time.time(), 'current': label})

snapshot = data_path('config/autosave/profile-test.toml', state=True)
snapshot.parent.mkdir(parents=True, exist_ok=True)
snapshot.write_text('output_name = "profile-test"\n', encoding='utf-8')
manager = TaskManager()
manager.enable_persistence()
manager.restore_queue()
previous_tasks = sorted(manager.tasks)
task = manager.create_task(
    [sys.executable, '-c', "print('profile task output')"], dict(os.environ),
    task_id=label, metadata={'log_file': 'logs/profile-test.log', 'config_path': str(snapshot)},
)
manager.submit(task)
deadline = time.monotonic() + 15
while time.monotonic() < deadline:
    try:
        records = json.loads(default_queue_path().read_text(encoding='utf-8'))
        done = any(item['task_id'] == label and item['status'] == 'FINISHED' for item in records)
    except (OSError, ValueError):
        done = False
    if done:
        break
    time.sleep(0.02)
assert done and task.status == TaskStatus.FINISHED
assert 'profile task output' in Path(task.log_file).read_text(encoding='utf-8')
print('PROFILE_RESULT=' + json.dumps({
    'label': label, 'previous_label': previous_label, 'previous_tasks': previous_tasks,
    'revision_before': revision, 'user_data': str(store.root), 'app_config': str(app_config.path),
    'queue': str(default_queue_path()), 'log': task.log_file,
    'archives': len(store.list_task_archives()),
}))
'''


def test_version_switch_preserves_preferences_and_isolates_queue_and_config(tmp_path):
    profile = tmp_path / "配置 空间"
    results = []
    for version, label in [("version-a", "first"), ("version-b", "second"), ("version-a", "third")]:
        source = tmp_path / "versions" / version / "app"
        source.mkdir(parents=True, exist_ok=True)
        state = profile / "compat" / version
        environment = {
            **os.environ, "PYTHONPATH": str(REPO), "PYTHONUTF8": "1",
            "NEXT_TRAINER_DATA_ROOT": str(profile), "NEXT_TRAINER_STATE_ROOT": str(state),
        }
        result = subprocess.run(
            [sys.executable, "-c", ROUNDTRIP, label], cwd=source, env=environment,
            text=True, capture_output=True, encoding="utf-8", errors="replace", timeout=25,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        line = next(line for line in result.stdout.splitlines() if line.startswith("PROFILE_RESULT="))
        record = json.loads(line.removeprefix("PROFILE_RESULT="))
        assert record["user_data"] == str(profile / "user_data")
        assert Path(record["app_config"]) == state / "assets/config.json"
        assert Path(record["queue"]) == state / "logs/task_queue.json"
        assert Path(record["log"]) == state / "logs/profile-test.log"
        assert not list(source.iterdir()), "Profile writes must not land in the version source directory"
        assert (state / "config/network.local.json").is_file()
        assert (state / "config/download-sources.local.json").is_file()
        assert (state / "config/.update_cache.json").is_file()
        results.append(record)
    assert [item["revision_before"] for item in results] == [0, 1, 2]
    assert [item["archives"] for item in results] == [1, 2, 3]
    assert [item["previous_label"] for item in results] == [None, None, "first"]
    assert [item["previous_tasks"] for item in results] == [[], [], ["first"]]
    assert [item["task_id"] for item in json.loads((profile / "compat/version-b/logs/task_queue.json").read_text())] == ["second"]

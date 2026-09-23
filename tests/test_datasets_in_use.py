import json
import time
from pathlib import Path

import pytest

from mikazuki.datasets import in_use
from mikazuki.tasks import Task, TaskStatus, tm


@pytest.fixture(autouse=True)
def clean_tasks(monkeypatch):
    monkeypatch.setattr(tm, "tasks", {})
    in_use.invalidate_in_use_cache()
    yield
    in_use.invalidate_in_use_cache()


def add_task(config_path: Path, status=TaskStatus.QUEUED, cwd: Path | None = None) -> Task:
    task = Task(f"task-{config_path.stem}", ["true"], metadata={"config_path": str(config_path.resolve()), "job_label": "Training", "cwd": str(cwd or config_path.parent)})
    task.status = status
    tm.tasks[task.task_id] = task
    in_use.invalidate_in_use_cache()
    return task


def write_toml(path: Path, body: str):
    path.write_text(body, encoding="utf-8")


def test_queued_task_marks_dataset_in_use(tmp_path):
    datasets = tmp_path / "datasets"
    (datasets / "ds-a").mkdir(parents=True)
    config = tmp_path / "conf.toml"
    write_toml(config, f'train_data_dir = "{(datasets / "ds-a").as_posix()}"\n')
    add_task(config)

    usage = in_use.in_use_map(datasets)

    assert [ref["task_id"] for ref in usage["ds-a"]] == ["task-conf"]


def test_finished_tasks_do_not_lock(tmp_path):
    datasets = tmp_path / "datasets"
    (datasets / "ds-a").mkdir(parents=True)
    config = tmp_path / "conf.toml"
    write_toml(config, f'train_data_dir = "{(datasets / "ds-a").as_posix()}"\n')
    add_task(config, status=TaskStatus.FINISHED)

    assert in_use.in_use_map(datasets) == {}


def test_diffsynth_json_arguments_and_control_dirs(tmp_path):
    datasets = tmp_path / "datasets"
    (datasets / "edit-set").mkdir(parents=True)
    config = tmp_path / "args.json"
    payload = {"arguments": {"train_data_dir": str(datasets / "elsewhere"), "control_data_dirs": [str(datasets / "edit-set" / "ref")]}}
    config.write_text(json.dumps(payload), encoding="utf-8")
    add_task(config)

    usage = in_use.in_use_map(datasets)

    assert "edit-set" in usage


def test_nested_dataset_config_reference(tmp_path):
    datasets = tmp_path / "datasets"
    (datasets / "ds-b").mkdir(parents=True)
    dataset_toml = tmp_path / "dataset.toml"
    write_toml(dataset_toml, f'[[datasets.subsets]]\nimage_dir = "{(datasets / "ds-b").as_posix()}"\n')
    config = tmp_path / "train.toml"
    write_toml(config, f'dataset_config = "{dataset_toml.as_posix()}"\n')
    add_task(config)

    usage = in_use.in_use_map(datasets)

    assert "ds-b" in usage


def test_relative_paths_resolve_against_task_cwd(tmp_path):
    datasets = tmp_path / "datasets"
    (datasets / "ds-c").mkdir(parents=True)
    config = tmp_path / "conf.toml"
    write_toml(config, 'train_data_dir = "./datasets/ds-c"\n')
    add_task(config, cwd=tmp_path)

    usage = in_use.in_use_map(datasets)

    assert "ds-c" in usage


def test_ancestor_path_locks_enclosed_datasets(tmp_path):
    datasets = tmp_path / "datasets"
    (datasets / "one").mkdir(parents=True)
    (datasets / "two").mkdir(parents=True)
    config = tmp_path / "conf.toml"
    write_toml(config, f'train_data_dir = "{datasets.as_posix()}"\n')
    add_task(config)

    usage = in_use.in_use_map(datasets)

    assert set(usage) == {"one", "two"}


def test_unrelated_config_leaves_datasets_unlocked(tmp_path):
    datasets = tmp_path / "datasets"
    (datasets / "ds-d").mkdir(parents=True)
    other = tmp_path / "other"
    other.mkdir()
    config = tmp_path / "conf.toml"
    write_toml(config, f'train_data_dir = "{other.as_posix()}"\n')
    add_task(config)

    assert in_use.in_use_map(datasets) == {}


def test_missing_config_file_is_skipped(tmp_path):
    datasets = tmp_path / "datasets"
    (datasets / "ds-e").mkdir(parents=True)
    task = Task("task-gone", ["true"], metadata={"config_path": str(tmp_path / "gone.toml")})
    task.status = TaskStatus.RUNNING
    tm.tasks[task.task_id] = task

    assert in_use.in_use_map(datasets) == {}


def test_result_is_cached_briefly(tmp_path):
    datasets = tmp_path / "datasets"
    (datasets / "ds-f").mkdir(parents=True)
    config = tmp_path / "conf.toml"
    write_toml(config, f'train_data_dir = "{(datasets / "ds-f").as_posix()}"\n')
    add_task(config)

    first = in_use.in_use_map(datasets)
    tm.tasks.clear()
    assert in_use.in_use_map(datasets) == first
    in_use.invalidate_in_use_cache()
    assert in_use.in_use_map(datasets) == {}

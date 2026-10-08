"""Caption archives and a projection into the existing TaskManager.

CaptionJobStore owns execution/recovery; this module never schedules inference.
Only jobs created with an archive are restored into the task page.
"""
from __future__ import annotations

import copy
import json
import os
import re
import stat
import tempfile
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from mikazuki.tasks import LANE_MAINTENANCE, TaskStatus, tm
from mikazuki.train_log_hub import hub
from mikazuki.log import log
from mikazuki.llm.prompt_presets import user_data_root
from .caption_store import REQUEST_FIELDS

_TERMINAL = {"done", "error", "cancelled"}


class CaptionTaskBridge:
    def __init__(self, root: Path | None = None, task_manager=None):
        self.root = Path(root or user_data_root()).absolute()
        self.task_manager = task_manager if task_manager is not None else tm
        self.locations: dict[str, Path] = {}

    def _contained(self, path: Path) -> Path:
        try:
            path.absolute().relative_to(self.root)
            path.resolve().relative_to(self.root.resolve())
        except ValueError:
            raise OSError("caption archive path is outside user_data") from None
        current = path.absolute()
        while True:
            if current.exists() or current.is_symlink():
                if current.is_symlink() or getattr(current.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                    raise OSError("caption archive cannot use symbolic links or junctions")
            if current == self.root:
                break
            current = current.parent
        return path

    def _write(self, path: Path, value: dict, *, backup: bool = False):
        self._contained(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if backup and path.is_file():
            prior = json.loads(path.read_text(encoding="utf-8"))
            self._write(path.with_suffix(".json.bak"), prior)
        descriptor, temporary = tempfile.mkstemp(prefix=".caption-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            self._contained(path)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def _read_record(self, path: Path) -> tuple[dict, bool]:
        self._contained(path)
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            recovered = False
        except json.JSONDecodeError:
            backup = self._contained(path.with_suffix(".json.bak"))
            record = json.loads(backup.read_text(encoding="utf-8"))
            recovered = True
        if not isinstance(record, dict):
            raise ValueError("caption archive is invalid")
        return record, recovered

    @staticmethod
    def _validate_id(job_id):
        if not isinstance(job_id, str) or str(UUID(job_id)) != job_id:
            raise ValueError("caption job id is invalid")

    def _location(self, relative: str, job_id: str) -> Path:
        self._validate_id(job_id)
        pattern = r"tasks/dataset-tagger/\d{4}-\d{2}-\d{2}/\d{6}_\d{6}_" + re.escape(job_id)
        if not isinstance(relative, str) or not re.fullmatch(pattern, relative):
            raise OSError("caption archive reference is invalid")
        return self._contained(self.root / relative)

    def prepare(self, state: dict, request: dict, paths: list[str], cancel_callback) -> str:
        job_id = state["job_id"]
        self._validate_id(job_id)
        timestamp = datetime.now(timezone(timedelta(hours=8)))
        relative = f"tasks/dataset-tagger/{timestamp:%Y-%m-%d}/{timestamp:%H%M%S_%f}_{job_id}"
        directory = self._location(relative, job_id)
        if directory.exists():
            raise OSError("caption archive already exists")
        config = {
            "schema_version": 1, "kind": "caption_snapshot", "job_id": job_id,
            "parameters": {key: copy.deepcopy(value) for key, value in request.items() if key in REQUEST_FIELDS and key != "_task_archive"},
            "images": list(paths),
        }
        # Both artifacts must be durable before registration or worker startup.
        self._write(directory / "config.json", config)
        self._write(directory / "task.json", {
            "schema_version": 1, "kind": "dataset_caption", "job_id": job_id,
            "created_at": timestamp.timestamp(), "hidden_from_tasks": False,
            "state": copy.deepcopy(state),
        })
        self.locations[job_id] = directory
        self._register(state, timestamp.timestamp(), cancel_callback)
        return relative

    def _register(self, state: dict, created_at: float, cancel_callback=None, *, restoring=False):
        job_id = state["job_id"]
        if job_id in self.task_manager.tasks:
            return
        log_path = self._contained(self.locations[job_id] / "task.log")
        task = self.task_manager.create_task(
            [], {"MIKAZUKI_TASK_KIND": "dataset_caption"}, task_id=job_id, lane=LANE_MAINTENANCE,
            metadata={"kind": "dataset_caption", "backend": "dataset-tagger", "caption_job_id": job_id, "created_at": created_at},
            on_cancel=cancel_callback or (lambda: None), on_delete=lambda: self.hide(job_id),
        )
        task.log_file = str(log_path)
        task.start_log_only()
        task.metadata["started_at"] = created_at
        self._project(state, restoring=restoring)
        if restoring and log_path.is_file():
            with log_path.open(encoding="utf-8") as stream:
                for line in deque(stream, maxlen=240):
                    hub.append_line(job_id, line)

    def _project(self, state: dict, *, restoring=False):
        task = self.task_manager.tasks.get(state["job_id"])
        if task is None:
            return
        old_phase = task.metadata.get("caption_phase")
        task.metadata.update({"caption_phase": state["phase"], "caption_current": state["current"], "caption_total": state["total"],
                              "caption_succeeded": state["succeeded"], "caption_skipped": state.get("skipped", 0), "caption_failed": state["failed"]})
        line = f"Caption {state['phase']}: {state['current']}/{state['total']}; success={state['succeeded']}; skipped={state.get('skipped', 0)}; failed={state['failed']}"
        self._contained(Path(task.log_file))
        if not restoring:
            hub.append_line(task.task_id, line)
            task._append_disk_log(line)
        if state["phase"] in _TERMINAL and old_phase not in _TERMINAL:
            failed = state["phase"] == "error" or bool(state["failed"])
            task.metadata.setdefault("finished_at", state.get("finished_at", state["updated_at"]))
            if restoring:
                task.returncode = 1 if failed else 0
                task.status = TaskStatus.FAILED if failed else TaskStatus.FINISHED
                task.metadata["returncode"] = task.returncode
                if failed:
                    task.metadata["error"] = "打标未全部完成，请查看逐文件报告"
                hub.mark_done(task.task_id)
            else:
                task.finish_log_only(1 if failed else 0, "自然语言打标未全部完成，请查看逐文件报告" if failed else None)
            if state["phase"] == "cancelled":
                task.status = TaskStatus.TERMINATED
                task.metadata.pop("error", None)
                task.metadata.pop("last_log_lines", None)

    def update(self, state: dict, request: dict):
        relative = request.get("_task_archive")
        if not relative:
            return
        job_id = state["job_id"]
        directory = self._location(relative, job_id)
        record_path = directory / "task.json"
        self._contained(record_path)
        record, recovered = self._read_record(record_path)
        if record.get("job_id") != job_id or record.get("kind") != "dataset_caption":
            raise OSError("caption archive does not match job")
        record["state"] = copy.deepcopy(state)
        self._write(record_path, record, backup=not recovered)
        self.locations[job_id] = directory
        self._project(state)

    def hide(self, job_id: str):
        directory = self.locations.get(job_id)
        if directory is None:
            return
        path = directory / "task.json"
        self._contained(path)
        record, recovered = self._read_record(path)
        if record["state"]["phase"] not in _TERMINAL:
            raise RuntimeError("请先结束打标任务")
        record["hidden_from_tasks"] = True
        self._write(path, record, backup=not recovered)

    def restore(self, job_store):
        base = self._contained(self.root / "tasks" / "dataset-tagger")
        if not base.is_dir():
            return
        for path in sorted(base.glob("*/*/task.json")):
            try:
                record, recovered = self._read_record(path)
                if record.get("schema_version") != 1 or record.get("kind") != "dataset_caption" or record.get("hidden_from_tasks"):
                    continue
                job_id = record["job_id"]
                directory = self._location(path.parent.relative_to(self.root).as_posix(), job_id)
                if not self._contained(directory / "config.json").is_file():
                    continue
                saved = job_store.get(job_id) if job_store else None
                state = copy.deepcopy(saved["state"] if saved else record["state"])
                if state["phase"] not in _TERMINAL:
                    state.update(phase="error", message="服务重启前未完成，可从打标页重试", recovered=True)
                self.locations[job_id] = directory
                if recovered or record["state"] != state:
                    record["state"] = state
                    self._write(path, record, backup=not recovered)
                self._register(state, record["created_at"], restoring=True)
            except (OSError, ValueError, KeyError):
                log.warning("Caption archive unavailable; other task records remain usable / 打标档案不可读，请检查user_data，其他记录继续可用")

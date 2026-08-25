import subprocess
import sys
import os
import json
import re
import threading
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from enum import Enum
from typing import Dict, List, Optional
from subprocess import Popen, PIPE, TimeoutExpired, CalledProcessError, CompletedProcess
import psutil

from mikazuki.log import log
from mikazuki.train_log_hub import hub

_FAILURE_LOG_TAIL_LINES = 80

LANE_COMPUTE = "compute"
LANE_MAINTENANCE = "maintenance"

# Env keys matching this pattern are never written to the queue file; on
# restore they are filled back from the current process environment.
_SENSITIVE_ENV_KEY = re.compile(r"TOKEN|KEY|SECRET|PASSWORD", re.IGNORECASE)

try:
    import msvcrt
    import _winapi
    _mswindows = True
except ModuleNotFoundError:
    _mswindows = False


def kill_proc_tree(pid, including_parent=True):
    parent = psutil.Process(pid)
    children = parent.children(recursive=True)
    for child in children:
        child.kill()
    gone, still_alive = psutil.wait_procs(children, timeout=5)
    if including_parent:
        parent.kill()
        parent.wait(5)


class TaskStatus(Enum):
    CREATED = 0
    RUNNING = 1
    FINISHED = 2
    TERMINATED = 3
    FAILED = 4
    QUEUED = 5


class Task:
    def __init__(self, task_id, command, environ=None, metadata=None, cwd=None,
                 lane=LANE_COMPUTE, group=None):
        self.task_id = task_id
        self.lock = threading.Lock()
        self.command = command
        self.status = TaskStatus.CREATED
        self.environ = environ or os.environ
        self.metadata = metadata or {}
        self.metadata.setdefault("created_at", datetime.now().timestamp())
        self.cwd = cwd
        self.lane = lane
        self.group = group
        self.returncode = None
        self.log_file = self.metadata.get("log_file")
        self._stdout_thread = None

    def _append_disk_log(self, text: str):
        if not self.log_file:
            return
        try:
            path = Path(self.log_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", errors="replace") as f:
                f.write(text)
                if text and not text.endswith("\n"):
                    f.write("\n")
        except Exception:
            pass

    def start_log_only(self):
        self.status = TaskStatus.RUNNING
        self.returncode = None
        self.metadata.pop("returncode", None)
        hub.start_task(self.task_id)

    def finish_log_only(self, returncode=0, error=None):
        self.returncode = returncode
        if error:
            self.metadata["error"] = str(error)
            self._append_disk_log(f"[error] {error}")
        self.status = TaskStatus.FINISHED if returncode == 0 else TaskStatus.FAILED
        self._append_disk_log(f"[task finished] returncode={returncode}")
        hub.mark_done(self.task_id)
        self._record_completion(returncode)

    def _join_stdout_pump(self):
        thread = self._stdout_thread
        if thread and thread.is_alive():
            thread.join(timeout=2)

    def _record_completion(self, returncode):
        self.metadata.setdefault("finished_at", datetime.now().timestamp())
        self.metadata["returncode"] = returncode
        if returncode == 0:
            self.metadata.pop("last_log_lines", None)
            if self.metadata.get("error") == "Training process exited with code 0":
                self.metadata.pop("error", None)
            return
        if self.status == TaskStatus.TERMINATED:
            # Manual stop: the nonzero exit (usually -9) is expected, don't
            # present it as a failure reason in the UI.
            return
        message = f"Training process exited with code {returncode}"
        self.metadata.setdefault("error", message)
        self.metadata["last_log_lines"] = hub.tail(self.task_id, _FAILURE_LOG_TAIL_LINES)

    def communicate(self, input=None, timeout=None):
        try:
            stdout, stderr = self.process.communicate(input, timeout=timeout)
        except TimeoutExpired as exc:
            self.process.kill()
            if _mswindows:
                exc.stdout, exc.stderr = self.process.communicate()
            else:
                self.process.wait()
            raise
        except:
            self.process.kill()
            raise
        retcode = self.process.poll()
        self.returncode = retcode
        self.status = TaskStatus.FINISHED if retcode == 0 else TaskStatus.FAILED
        self._append_disk_log(f"[task communicate finished] returncode={retcode}")
        self._record_completion(retcode)
        return CompletedProcess(self.process.args, retcode, stdout, stderr)

    def wait(self):
        retcode = self.process.wait()
        self._join_stdout_pump()
        self.returncode = retcode
        if self.status != TaskStatus.TERMINATED:
            self.status = TaskStatus.FINISHED if retcode == 0 else TaskStatus.FAILED
        self._append_disk_log(f"[task wait finished] returncode={retcode}")
        self._record_completion(retcode)

    def _stdout_pump(self):
        """Drain child stdout into TrainLogHub AND echo to parent console."""
        try:
            if not self.process or self.process.stdout is None:
                return
            for line in iter(self.process.stdout.readline, ""):
                hub.append_line(self.task_id, line)
                self._append_disk_log(line)
                try:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                except Exception:
                    pass
        except Exception as e:
            hub.append_line(self.task_id, f"[stdout pump] {e}")
            self._append_disk_log(f"[stdout pump] {e}")
        finally:
            try:
                if self.process and self.process.stdout:
                    self.process.stdout.close()
            except Exception:
                pass
            hub.mark_done(self.task_id)

    def execute(self):
        self.status = TaskStatus.RUNNING
        self.returncode = None
        self.metadata.pop("returncode", None)
        # Insights use started_at (not created_at) as the lower bound so queued
        # tasks don't pick up data written by the previous task while waiting.
        self.metadata["started_at"] = datetime.now().timestamp()
        hub.start_task(self.task_id)
        self._append_disk_log(
            "\n"
            f"[task start] {datetime.now().isoformat(timespec='seconds')}\n"
            f"task_id={self.task_id}\n"
            f"cwd={self.cwd or os.getcwd()}\n"
            f"command={' '.join(map(str, self.command))}\n"
        )
        try:
            self.process = subprocess.Popen(
                self.command,
                env=self.environ,
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as e:
            hub.append_line(self.task_id, f"[error] Failed to start training process: {e}")
            self._append_disk_log(f"[error] Failed to start training process: {e}")
            hub.mark_done(self.task_id)
            self.status = TaskStatus.FAILED
            self.returncode = -1
            self.metadata["returncode"] = -1
            self.metadata["error"] = str(e)
            raise
        self._stdout_thread = threading.Thread(target=self._stdout_pump, daemon=True)
        self._stdout_thread.start()

    def terminate(self):
        # Mark TERMINATED before killing: the worker's wait() returns as soon
        # as the process dies and must already see the final status, otherwise
        # _record_completion() races and logs the -9 exit as a failure.
        self.status = TaskStatus.TERMINATED
        try:
            # Kill the whole tree, launcher included: accelerate's elastic
            # agent respawns killed workers, so killing only children leaves
            # a zombie that blocks the worker's task.wait() forever (#286).
            kill_proc_tree(self.process.pid, True)
        except Exception as e:
            log.error(f"Error when killing process: {e}")
        finally:
            self._append_disk_log("[task terminated]")


class TaskManager:
    """Two lanes: compute tasks (training) run serially through a FIFO queue
    driven by a worker thread; maintenance tasks (install/download) run in
    parallel and never block the compute lane."""

    def __init__(self, max_concurrent=1, persist_path: Optional[Path] = None) -> None:
        self.max_concurrent = max_concurrent
        self.tasks: Dict[str, Task] = {}
        self._cond = threading.Condition()
        self._compute_queue: deque = deque()
        self._worker: Optional[threading.Thread] = None
        self._persist_path: Optional[Path] = Path(persist_path) if persist_path else None

    # ---- queue persistence ----

    def enable_persistence(self, path: Optional[Path] = None):
        """Declare the queue file location only. Must NOT persist here: at
        startup the task table is still empty, and writing now would wipe the
        file before restore_queue() reads it."""
        self._persist_path = Path(path) if path else default_queue_path()

    def _task_record(self, task: Task) -> Dict:
        env = {
            str(k): str(v) for k, v in (task.environ or {}).items()
            if not _SENSITIVE_ENV_KEY.search(str(k))
        }
        return {
            "task_id": task.task_id,
            "lane": task.lane,
            "group": task.group,
            "command": [str(part) for part in task.command],
            "cwd": str(task.cwd) if task.cwd else None,
            "metadata": task.metadata,
            "env": env,
            "status": task.status.name,
        }

    def _persist(self):
        """Snapshot the compute lane (pending work AND terminal history)
        atomically. Terminal tasks stay on disk until an explicit
        delete_task()/purge_tasks() removes them; there is no auto cleanup."""
        if not self._persist_path:
            return
        try:
            records = [
                self._task_record(t) for t in self.tasks.values()
                if t.lane == LANE_COMPUTE and t.status != TaskStatus.CREATED
            ]
            path = self._persist_path
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, path)
        except Exception as e:
            log.warning(f"Failed to persist task queue / 任务队列持久化失败: {e}")

    def restore_queue(self):
        """Re-enqueue tasks persisted as QUEUED; mark interrupted RUNNING as
        FAILED; restore terminal tasks as read-only history (never queued)."""
        path = self._persist_path
        if not path or not path.is_file():
            return
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"Task queue file corrupt, starting empty / 队列文件损坏，按空队列启动: {e}")
            try:
                os.replace(path, path.with_suffix(path.suffix + ".corrupt"))
            except Exception:
                pass
            return
        restored = 0
        with self._cond:
            for record in records:
                if not isinstance(record, dict):
                    continue
                task_id = record.get("task_id")
                if not task_id or task_id in self.tasks:
                    continue
                if record.get("status") == "QUEUED":
                    stored_env = record.get("env") or {}
                    environ = {**os.environ, **stored_env}
                    task = Task(
                        task_id=task_id,
                        command=record.get("command") or [],
                        environ=environ,
                        metadata=record.get("metadata") or {},
                        cwd=record.get("cwd"),
                        lane=LANE_COMPUTE,
                        group=record.get("group"),
                    )
                    task.status = TaskStatus.QUEUED
                    # Restored tasks never auto-start: a restart usually means
                    # the operator changed something, so require a manual resume.
                    task.metadata["held"] = True
                    self.tasks[task_id] = task
                    self._compute_queue.append(task_id)
                    restored += 1
                elif record.get("status") in ("FINISHED", "FAILED", "TERMINATED"):
                    # Terminal history: restore as-is for the workbench list;
                    # never queued, never held, deletable/retryable as usual.
                    stored_env = record.get("env") or {}
                    task = Task(
                        task_id=task_id,
                        command=record.get("command") or [],
                        environ={**os.environ, **stored_env},
                        metadata=record.get("metadata") or {},
                        cwd=record.get("cwd"),
                        lane=LANE_COMPUTE,
                        group=record.get("group"),
                    )
                    task.status = TaskStatus[record["status"]]
                    returncode = task.metadata.get("returncode")
                    task.returncode = returncode if isinstance(returncode, int) else None
                    self.tasks[task_id] = task
                elif record.get("status") == "RUNNING":
                    # Keep the stored env: the interrupted task stays retryable,
                    # and training commands rely on env like PYTHONPATH (#158).
                    stored_env = record.get("env") or {}
                    task = Task(
                        task_id=task_id,
                        command=record.get("command") or [],
                        environ={**os.environ, **stored_env},
                        metadata=record.get("metadata") or {},
                        cwd=record.get("cwd"),
                        lane=LANE_COMPUTE,
                        group=record.get("group"),
                    )
                    task.status = TaskStatus.FAILED
                    task.returncode = -1
                    task.metadata["returncode"] = -1
                    task.metadata.setdefault("finished_at", datetime.now().timestamp())
                    task.metadata["error"] = (
                        "interrupted by server restart / 服务重启导致任务中断")
                    self.tasks[task_id] = task
            if restored:
                self._ensure_worker_locked()
                self._cond.notify_all()
        if restored:
            log.info(f"Restored {restored} queued task(s) / 已恢复 {restored} 个排队任务")
        self._persist()

    def _compute_busy_locked(self) -> bool:
        if self._compute_queue:
            return True
        return any(
            t.lane == LANE_COMPUTE and t.status == TaskStatus.RUNNING
            for t in self.tasks.values()
        )

    def create_task(self, command: List[str], environ, metadata=None, cwd=None,
                    task_id=None, lane=LANE_COMPUTE, group=None) -> Task:
        """Register a task. Compute tasks are queued (never rejected) when the
        lane is busy; call submit()/submit_group() to schedule execution."""
        with self._cond:
            task_id = task_id or str(uuid.uuid4())
            task = Task(task_id=task_id, command=command, environ=environ,
                        metadata=metadata, cwd=cwd, lane=lane, group=group)
            if lane == LANE_COMPUTE and self._compute_busy_locked():
                task.status = TaskStatus.QUEUED
                log.info(f"Task {task_id} created and queued (compute lane busy) / 任务已加入队列")
            else:
                log.info(f"Task {task_id} created")
            self.tasks[task_id] = task
            self._persist()
            return task

    def add_task(self, task_id: str, task: Task):
        """Low-level registration without lane checks. Kept for tests and
        state-reconciliation code; production paths must use create_task()."""
        self.tasks[task_id] = task

    def submit(self, task: Task):
        self.submit_group([task])

    def submit_group(self, tasks: List[Task]):
        """Schedule compute tasks for serial execution by the worker thread.
        Group members submitted together run contiguously in submission order."""
        with self._cond:
            for task in tasks:
                if task.status in (TaskStatus.CREATED, TaskStatus.QUEUED) \
                        and task.task_id not in self._compute_queue:
                    self._compute_queue.append(task.task_id)
            self._ensure_worker_locked()
            self._cond.notify_all()
            self._persist()

    def _ensure_worker_locked(self):
        if self._worker and self._worker.is_alive():
            return
        self._worker = threading.Thread(
            target=self._worker_loop, daemon=True, name="tm-compute-worker")
        self._worker.start()

    def _worker_loop(self):
        while True:
            with self._cond:
                task = None
                while task is None:
                    for task_id in list(self._compute_queue):
                        candidate = self.tasks.get(task_id)
                        if candidate is None or candidate.status not in (TaskStatus.CREATED, TaskStatus.QUEUED):
                            self._compute_queue.remove(task_id)
                            continue
                        if candidate.metadata.get("held"):
                            continue  # restored from disk, waiting for manual resume
                        self._compute_queue.remove(task_id)
                        task = candidate
                        break
                    if task is None:
                        self._cond.wait()
            self._run_compute_task(task)
            self._persist()

    def _run_compute_task(self, task: Task):
        label = task.metadata.get("job_label") or "Training"
        rc = -1
        try:
            task.execute()
            self._persist()  # RUNNING now; crash before completion -> marked interrupted on restore
            task.wait()
            rc = task.process.returncode if task.process else -1
            if rc != 0:
                log.error(f"{label} failed / 任务失败 (exit {rc})")
            else:
                log.info(f"{label} finished / 任务完成")
        except Exception as e:
            log.error(f"{label} fatal error / 任务出现致命错误: {e}")
        if rc != 0 and task.group:
            self._skip_group_remainder(task, rc)

    def _skip_group_remainder(self, failed_task: Task, rc: int):
        label = failed_task.metadata.get("stage_label") \
            or failed_task.metadata.get("job_label") \
            or failed_task.task_id
        message = f"上一阶段「{label}」失败 (exit {rc})，已跳过"
        for other in self.tasks.values():
            if other is failed_task or other.group != failed_task.group or not other.group:
                continue
            if other.status not in (TaskStatus.CREATED, TaskStatus.QUEUED):
                continue
            other.status = TaskStatus.FAILED
            other.returncode = -1
            other.metadata["returncode"] = -1
            other.metadata.setdefault("finished_at", datetime.now().timestamp())
            other.metadata["error"] = message
            log.warning(f"Task {other.task_id} skipped: {message}")
            with self._cond:
                try:
                    self._compute_queue.remove(other.task_id)
                except ValueError:
                    pass
        self._persist()

    def terminate_task(self, task_id: str):
        task = self.tasks.get(task_id)
        if task is None:
            return
        if task.status in (TaskStatus.CREATED, TaskStatus.QUEUED) \
                and not hasattr(task, "process"):
            # Still waiting in the queue: drop it without touching any process.
            task.status = TaskStatus.TERMINATED
            task.metadata.setdefault("finished_at", datetime.now().timestamp())
            task._append_disk_log("[task terminated while queued]")
            with self._cond:
                try:
                    self._compute_queue.remove(task_id)
                except ValueError:
                    pass
                self._cond.notify_all()
            self._persist()
            log.info(f"Task {task_id} removed from queue / 排队任务已移出队列")
            return
        task.terminate()

    def move_to_front(self, task_id: str) -> bool:
        """Move a queued compute task (held or not) to the front of the queue,
        i.e. right after the currently running task. Stage groups move as a
        whole, preserving stage order and contiguity."""
        with self._cond:
            task = self.tasks.get(task_id)
            if task is None or task_id not in self._compute_queue:
                return False
            if task.group:
                members = [
                    t for t in self.tasks.values()
                    if t.group == task.group and t.task_id in self._compute_queue
                ]
                members.sort(key=lambda t: list(self._compute_queue).index(t.task_id))
                ids = [t.task_id for t in members]
            else:
                ids = [task_id]
            for tid in ids:
                self._compute_queue.remove(tid)
            for tid in reversed(ids):
                self._compute_queue.appendleft(tid)
            self._persist()
        log.info(f"Task {task_id} moved to queue front ({len(ids)} task(s)) / 任务已提到队列最前")
        return True

    def resume_task(self, task_id: str) -> bool:
        """Release a restored (held) queued task so the worker may run it."""
        task = self.tasks.get(task_id)
        if task is None or task.status != TaskStatus.QUEUED or not task.metadata.get("held"):
            return False
        task.metadata.pop("held", None)
        with self._cond:
            self._cond.notify_all()
        self._persist()
        log.info(f"Task {task_id} resumed from hold / 排队任务已确认开始")
        return True

    _RETRY_STRIP_METADATA = ("error", "returncode", "finished_at", "last_log_lines", "held", "started_at")

    _TERMINAL_STATUSES = (TaskStatus.FINISHED, TaskStatus.FAILED, TaskStatus.TERMINATED)

    def delete_task(self, task_id: str) -> bool:
        """Remove a terminal task from the table. Active tasks are refused so
        a running training can never be dropped from under the worker."""
        with self._cond:
            task = self.tasks.get(task_id)
            if task is None or task.status not in self._TERMINAL_STATUSES:
                return False
            try:
                self._compute_queue.remove(task_id)
            except ValueError:
                pass
            del self.tasks[task_id]
            hub.drop_task(task_id)
            self._persist()
        log.info(f"Task {task_id} deleted / 任务已删除")
        return True

    def purge_tasks(self, keep_last: int = 0) -> int:
        """Bulk-delete terminal tasks, keeping the most recent ``keep_last``."""
        with self._cond:
            terminal = [t for t in self.tasks.values() if t.status in self._TERMINAL_STATUSES]
            terminal.sort(
                key=lambda t: float(
                    t.metadata["finished_at"] if t.metadata.get("finished_at") is not None
                    else (t.metadata.get("created_at") or 0)
                ),
                reverse=True,
            )
            doomed = terminal[max(0, keep_last):]
            for task in doomed:
                try:
                    self._compute_queue.remove(task.task_id)
                except ValueError:
                    pass
                del self.tasks[task.task_id]
                hub.drop_task(task.task_id)
            if doomed:
                self._persist()
        if doomed:
            log.info(f"Purged {len(doomed)} finished task(s) / 已清理 {len(doomed)} 个历史任务")
        return len(doomed)

    def retry_task(self, task_id: str) -> Optional[List[Task]]:
        """Re-queue a finished/failed/terminated compute task. Musubi-style
        stage groups are rebuilt as a whole, in stage order."""
        origin = self.tasks.get(task_id)
        if origin is None or origin.lane != LANE_COMPUTE or not origin.command:
            return None
        if origin.status not in (TaskStatus.FINISHED, TaskStatus.FAILED, TaskStatus.TERMINATED):
            return None
        if origin.group:
            stage_rank = {"cache_latents": 0, "cache_text_encoder": 1, "train": 2}
            members = [t for t in self.tasks.values() if t.group == origin.group]
            members.sort(key=lambda t: (stage_rank.get(str(t.metadata.get("stage")), 99),
                                        float(t.metadata.get("created_at") or 0)))
        else:
            members = [origin]
        new_group = str(uuid.uuid4()) if origin.group else None
        new_tasks: List[Task] = []
        for member in members:
            metadata = dict(member.metadata)
            for key in self._RETRY_STRIP_METADATA:
                metadata.pop(key, None)
            metadata["retry_of"] = member.task_id
            if new_group:
                metadata["train_task_id"] = new_group
            new_tasks.append(self.create_task(
                list(member.command), dict(member.environ or os.environ),
                metadata=metadata, cwd=member.cwd, group=new_group,
            ))
        self.submit_group(new_tasks)
        log.info(f"Task {task_id} re-queued ({len(new_tasks)} task(s)) / 任务已重新排队")
        return new_tasks

    def wait_for_process(self, task_id: str):
        if task_id in self.tasks:
            task: Task = self.tasks[task_id]
            task.wait()

    def queue_position(self, task_id: str) -> Optional[int]:
        with self._cond:
            try:
                return list(self._compute_queue).index(task_id) + 1
            except ValueError:
                return None

    def dump(self) -> List[Dict]:
        with self._cond:
            order = {tid: i + 1 for i, tid in enumerate(self._compute_queue)}
            return [
                {
                    "id": task.task_id,
                    "status": task.status.name,
                    "metadata": task.metadata,
                    "returncode": task.returncode,
                    "lane": task.lane,
                    "queue_position": order.get(task.task_id),
                }
                for task in self.tasks.values()
            ]


def default_queue_path() -> Path:
    return Path(os.environ.get("MIKAZUKI_TASK_QUEUE_FILE", "").strip() or (Path.cwd() / "logs" / "task_queue.json"))


tm = TaskManager()

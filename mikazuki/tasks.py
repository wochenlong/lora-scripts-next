import subprocess
import sys
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from enum import Enum
from typing import Dict, List
from subprocess import Popen, PIPE, TimeoutExpired, CalledProcessError, CompletedProcess
import psutil

from mikazuki.log import log
from mikazuki.train_log_hub import hub

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


class Task:
    def __init__(self, task_id, command, environ=None, metadata=None, cwd=None):
        self.task_id = task_id
        self.lock = threading.Lock()
        self.command = command
        self.status = TaskStatus.CREATED
        self.environ = environ or os.environ
        self.metadata = metadata or {}
        self.cwd = cwd
        self.returncode = None
        self.log_file = self.metadata.get("log_file")

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
        self.metadata["returncode"] = returncode
        if error:
            self.metadata["error"] = str(error)
            self._append_disk_log(f"[error] {error}")
        self.status = TaskStatus.FINISHED if returncode == 0 else TaskStatus.FAILED
        self._append_disk_log(f"[task finished] returncode={returncode}")
        hub.mark_done(self.task_id)

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
        self.metadata["returncode"] = retcode
        self.status = TaskStatus.FINISHED if retcode == 0 else TaskStatus.FAILED
        self._append_disk_log(f"[task communicate finished] returncode={retcode}")
        return CompletedProcess(self.process.args, retcode, stdout, stderr)

    def wait(self):
        retcode = self.process.wait()
        self.returncode = retcode
        self.metadata["returncode"] = retcode
        if self.status != TaskStatus.TERMINATED:
            self.status = TaskStatus.FINISHED if retcode == 0 else TaskStatus.FAILED
        self._append_disk_log(f"[task wait finished] returncode={retcode}")

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
        threading.Thread(target=self._stdout_pump, daemon=True).start()

    def terminate(self):
        try:
            kill_proc_tree(self.process.pid, False)
        except Exception as e:
            log.error(f"Error when killing process: {e}")
            return
        finally:
            self.status = TaskStatus.TERMINATED
            self._append_disk_log("[task terminated]")


class TaskManager:
    def __init__(self, max_concurrent=1) -> None:
        self.max_concurrent = max_concurrent
        self.tasks: Dict[Task] = {}

    def create_task(self, command: List[str], environ, metadata=None, cwd=None, task_id=None):
        running_tasks = [t for _, t in self.tasks.items() if t.status == TaskStatus.RUNNING]
        if len(running_tasks) >= self.max_concurrent:
            log.error(
                f"Unable to create a task because there are already {len(running_tasks)} tasks running, reaching the maximum concurrent limit. / 无法创建任务，因为已经有 {len(running_tasks)} 个任务正在运行，已达到最大并发限制。")
            return None
        task_id = task_id or str(uuid.uuid4())
        task = Task(task_id=task_id, command=command, environ=environ, metadata=metadata, cwd=cwd)
        self.tasks[task_id] = task
        # task.execute() # breaking change
        log.info(f"Task {task_id} created")
        return task

    def add_task(self, task_id: str, task: Task):
        self.tasks[task_id] = task

    def terminate_task(self, task_id: str):
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.terminate()

    def wait_for_process(self, task_id: str):
        if task_id in self.tasks:
            task: Task = self.tasks[task_id]
            task.wait()

    def dump(self) -> List[Dict]:
        return [
            {
                "id": task.task_id,
                "status": task.status.name,
                "metadata": task.metadata,
                "returncode": task.returncode,
            }
            for task in self.tasks.values()
        ]


tm = TaskManager()

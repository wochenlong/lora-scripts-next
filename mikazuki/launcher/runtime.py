"""启动器运行目录和跨进程工作区/目标引擎 lease（仅标准库）。"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time


ENGINE_LEASE_PROTOCOL = "engine-leases-v1"


class ControlError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class QueryStopped(ControlError):
    """查询取消/期限不得被完整性或缺资产的普通错误处理吞掉。"""


_QUERY_CONTROL = ContextVar("launcher_query_control", default=None)
QUERY_CHUNK_BYTES = 1024 * 1024
QUERY_STAGES = frozenset({"worker", "receipt", "environment", "source", "python", "extra_files", "tools"})
QUERY_MESSAGES = {
    "worker": "正在准备独立检查", "receipt": "正在核对安装记录", "environment": "正在核对环境文件",
    "source": "正在核对源码文件", "python": "正在核对基础 Python", "extra_files": "正在核对额外文件",
    "tools": "正在核对固定资产",
}


class QueryControl:
    """只读、无文件写入。父Rust是取消/动态期限及Job回收的权威。"""

    def __init__(self, task_id, remaining_ms, scope, *, progress=True, emit=None, clock=None, cancelled=None):
        self.task_id, self.scope = task_id, scope
        self.clock = clock or time.monotonic
        self.deadline = self.clock() + remaining_ms / 1000
        self.cancelled = cancelled  # 仅可信同进程调用/测试；不从JSON反序列化可执行对象。
        self.emit = emit if progress else None
        self.stage = "worker"
        self.files = self.bytes = self.seq = 0
        self.last_emitted = None
        self.last_payload = None

    @classmethod
    def from_request(cls, request, *, emit=None):
        if not isinstance(request, dict) or "query_protocol" not in request:
            return None
        protocol = request["query_protocol"]
        if not isinstance(protocol, dict) or type(protocol.get("version")) is not int or protocol["version"] != 1:
            raise ControlError("query_protocol_invalid", "查询协议版本不支持")
        task_id = protocol.get("task_id")
        remaining = protocol.get("remaining_ms")
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,191}", task_id):
            raise ControlError("query_protocol_invalid", "查询任务标识无效")
        if type(remaining) is not int or not 0 <= remaining <= 1800000 or type(protocol.get("progress")) is not bool:
            raise ControlError("query_protocol_invalid", "查询期限或进度开关无效")
        if "cancel_file" in request:
            raise ControlError("query_protocol_invalid", "只读查询不使用取消文件")
        action, scope = request.get("action"), protocol.get("scope", "full")
        allowed = {"capabilities": {"full"}, "recipe": {"full"}, "inspect_readonly": {"full", "files_only"},
                   "plan_install": {"plan"}, "plan_repair": {"plan"}}
        if not isinstance(action, str) or not isinstance(scope, str) or scope not in allowed.get(action, set()):
            raise ControlError("query_scope_invalid", "查询动作与范围不匹配")
        return cls(task_id, remaining, scope, progress=protocol["progress"], emit=emit)

    def check(self):
        if self.cancelled is not None and self.cancelled():
            raise QueryStopped("query_cancelled", "独立检查已取消")
        if self.clock() >= self.deadline:
            raise QueryStopped("query_timed_out", "独立检查已到入口总期限")

    def publish(self, *, force=False):
        self.check()
        if self.emit is None or self.seq >= 8192:
            return
        now = self.clock()
        payload = (self.stage, self.files, self.bytes)
        if self.last_payload == payload:
            return
        if not force and self.last_emitted is not None and now - self.last_emitted < 0.25:
            return
        frame = {"schema_version": 1, "type": "progress", "task_id": self.task_id, "seq": self.seq + 1,
                 "stage": self.stage, "files": self.files, "bytes": self.bytes,
                 "total_files": None, "total_bytes": None, "message": QUERY_MESSAGES[self.stage]}
        try:
            self.emit(frame)
        except (OSError, ValueError) as error:
            raise QueryStopped("query_output_closed", "查询进度管道已关闭") from error
        self.seq += 1
        self.last_emitted, self.last_payload = now, payload

    def set_stage(self, stage):
        self.check()
        if stage not in QUERY_STAGES:
            raise ControlError("query_stage_invalid", "不支持的查询阶段")
        if stage != self.stage:
            self.publish(force=True)
            self.stage, self.files, self.bytes = stage, 0, 0
            self.publish(force=True)
        else:
            self.publish()

    def checkpoint(self, *, read_bytes=0, file_complete=False):
        self.bytes += read_bytes
        self.files += int(file_complete)
        self.check()
        self.publish()


@contextmanager
def query_scope(control):
    token = _QUERY_CONTROL.set(control)
    try:
        if control is not None:
            control.check()
            control.publish(force=True)
        yield
    finally:
        _QUERY_CONTROL.reset(token)


def query_control():
    return _QUERY_CONTROL.get()


def query_checkpoint(*, read_bytes=0, file_complete=False):
    control = _QUERY_CONTROL.get()
    if control is not None:
        control.checkpoint(read_bytes=read_bytes, file_complete=file_complete)


def query_stage(stage):
    control = _QUERY_CONTROL.get()
    if control is not None:
        control.set_stage(stage)


def component(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,95}", value) or value in {".", ".."}:
        raise ControlError("invalid_component", "路径标识不符合受管合同")
    return value


def relative(value: str) -> Path:
    if not isinstance(value, str) or "\\" in value or ":" in value or "\x00" in value:
        raise ControlError("invalid_relative_path", "只接受固定相对 POSIX 路径")
    p = Path(value)
    if p.is_absolute() or not p.parts or any(x in {"", ".", ".."} for x in value.split("/")):
        raise ControlError("invalid_relative_path", "相对路径不得包含空段或父路径")
    return p


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    query_checkpoint()
    with path.open("rb") as stream:
        while True:
            query_checkpoint()
            chunk = stream.read(QUERY_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            query_checkpoint(read_bytes=len(chunk))
    query_checkpoint(file_complete=True)
    return digest.hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest_json(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def read_json(path: Path, limit: int = 32 * 1024 * 1024):
    query_checkpoint()
    if path.stat().st_size > limit:
        raise ControlError("state_too_large", "状态超过读取上限")
    if query_control() is not None:
        data = bytearray()
        with path.open("rb") as stream:
            while True:
                query_checkpoint()
                chunk = stream.read(min(QUERY_CHUNK_BYTES, limit + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                query_checkpoint(read_bytes=len(chunk))
                if len(data) > limit:
                    raise ControlError("state_too_large", "状态超过读取上限")
        query_checkpoint()
        value = json.loads(data.decode("utf-8"))
        query_checkpoint()
        return value
    return json.loads(path.read_text(encoding="utf-8"))


def is_reparse(path: Path) -> bool:
    metadata = path.lstat()
    return stat.S_ISLNK(metadata.st_mode) or bool(getattr(metadata, "st_file_attributes", 0) & 0x400)


def guard(path: Path, root: Path) -> Path:
    """词法归属和所有现存父级均核验；不 resolve 后再接受外指。"""
    path = Path(os.path.abspath(path))
    root = Path(os.path.abspath(root))
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ControlError("outside_workspace", "目标位于受管目录外") from error
    for item in [path, *path.parents]:
        if item.exists() or item.is_symlink():
            if is_reparse(item):
                raise ControlError("unexpected_reparse", f"受管物理路径拒绝链接：{item}")
    return path


@dataclass(frozen=True)
class RuntimeLayout:
    root: Path
    release_id: str
    engine_id: str
    instance_id: str = ""
    profile_id: str = "default"

    def __post_init__(self):
        root = Path(os.path.abspath(self.root))
        if not Path(self.root).is_absolute() or root.parent == root:
            raise ControlError("invalid_root", "工作区必须为独立绝对路径")
        component(self.release_id)
        component(self.profile_id)
        if self.engine_id not in {"kohya", "anima-fast", "ai-toolkit", "diffsynth"}:
            raise ControlError("unsupported_engine", "未适配该引擎")
        if self.instance_id and not re.fullmatch(r"t[a-f0-9]{15}", self.instance_id):
            raise ControlError("invalid_instance", "训练环境实例必须为 t 加 15 位十六进制")
        object.__setattr__(self, "root", root)
        guard(root, root)

    @property
    def source_root(self):
        return self.root / "releases" / self.release_id / "app"

    @property
    def run_root(self):
        return self.root / "run" / self.release_id

    @property
    def profile_root(self):
        return self.root / "profiles" / self.profile_id

    @property
    def state_root(self):
        return self.root / "state" / "engines" / self.release_id / self.engine_id

    @property
    def state_file(self):
        return self.state_root / "state.json"

    @property
    def base_python_root(self):
        return self.root / "p" / self.instance_id

    @property
    def environment_root(self):
        if not self.instance_id:
            raise ControlError("missing_instance", "缺少训练环境实例身份")
        return self.root / "e" / self.instance_id

    @property
    def engine_source_root(self):
        return self.root / "s" / self.instance_id

    @property
    def python(self):
        return self.environment_root / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")

    def checked(self, path: Path) -> Path:
        return guard(path, self.root)

    def as_dict(self):
        result = {name: str(getattr(self, name)) for name in ("root", "source_root", "run_root", "profile_root", "state_root", "base_python_root", "engine_source_root")}
        result.update(release_id=self.release_id, engine_id=self.engine_id, instance_id=self.instance_id, profile_id=self.profile_id)
        if self.instance_id:
            result.update(environment_root=str(self.environment_root), python=str(self.python))
        return result


def _owned_workspace(layout: RuntimeLayout):
    marker = layout.checked(layout.root / ".launcher-workspace")
    if not marker.is_file() or marker.read_text(encoding="utf-8") != "next-trainer-desktop-v1":
        raise ControlError("unowned_workspace", "只可修改正式启动器工作区")


def _lock_file(stream, *, shared=False):
    """与 Rust fs2 兼容：Windows 首字节，Unix flock；所有获取均不等待。"""
    if os.name == "nt":
        import ctypes
        import msvcrt
        from ctypes import wintypes
        # CRT 的 LK_NBRLCK 在 Windows 仍是独占锁；必须直接使用共享 LockFileEx。
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        call = kernel.LockFileEx
        call.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                         wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
        call.restype = wintypes.BOOL
        overlap = ctypes.create_string_buffer(32)
        if not call(msvcrt.get_osfhandle(stream.fileno()), 1 if shared else 3, 0, 1, 0, overlap):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        import fcntl
        fcntl.flock(stream, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)


def _unlock_file(stream):
    if os.name == "nt":
        import ctypes
        import msvcrt
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        call = kernel.UnlockFileEx
        call.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                         wintypes.DWORD, ctypes.c_void_p]
        call.restype = wintypes.BOOL
        overlap = ctypes.create_string_buffer(32)
        if not call(msvcrt.get_osfhandle(stream.fileno()), 0, 1, 0, overlap):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        import fcntl
        fcntl.flock(stream, fcntl.LOCK_UN)


@contextmanager
def _file_lease(path: Path, *, shared=False, code, message):
    with path.open("a+b") as stream:
        try:
            _lock_file(stream, shared=shared)
        except OSError as error:
            raise ControlError(code, message) from error
        try:
            yield
        finally:
            _unlock_file(stream)


@contextmanager
def workspace_lease(layout: RuntimeLayout, *, shared=False):
    """本体变更独占；服务、训练和独立引擎操作共享生命周期门。"""
    _owned_workspace(layout)
    path = layout.checked(layout.root / ".launcher-lock")
    with _file_lease(path, shared=shared, code="workspace_busy", message="工作区正在更新主程序或切换版本，请稍后重试"):
        yield


def _engine_lock_path(layout: RuntimeLayout):
    # 引擎实例可能跨发布版本复用，因此锁不能按 release 分割。
    return layout.checked(layout.root / "state" / "engine-locks" / (layout.engine_id + ".lock"))


@contextmanager
def engine_lease(layout: RuntimeLayout, *, mode="mutation"):
    """训练和预检共享使用目标；安装、修复、恢复及主动探测独占目标。"""
    if mode not in {"mutation", "training"}:
        raise ValueError("unknown engine lease mode")
    with workspace_lease(layout, shared=True):
        path = _engine_lock_path(layout)
        path.parent.mkdir(parents=True, exist_ok=True)
        layout.checked(path)
        with _file_lease(path, shared=mode == "training", code="engine_busy",
                         message=f"{layout.engine_id} 正在训练、被占用或已有安装修复任务；请等待该引擎空闲后重试"):
            yield


def engine_activity(layout: RuntimeLayout):
    """只读观察现有锁；不创建锁文件，也不代替执行时的原子冲突检查。"""
    path = _engine_lock_path(layout)
    idle = {"busy": False, "kind": "idle", "message": ""}
    if not path.exists():
        return idle
    try:
        with path.open("r+b") as stream:
            try:
                _lock_file(stream)
            except OSError:
                try:
                    _lock_file(stream, shared=True)
                except OSError:
                    return {"busy": True, "kind": "operation", "message": f"{layout.engine_id} 已有安装、修复或探测任务"}
                else:
                    _unlock_file(stream)
                    return {"busy": True, "kind": "training", "message": f"{layout.engine_id} 正在训练或执行训练预检"}
            else:
                _unlock_file(stream)
                return idle
    except FileNotFoundError:
        return idle

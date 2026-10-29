"""启动器运行目录和跨进程写 lease（仅标准库）。"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat


class ControlError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


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
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
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
    if path.stat().st_size > limit:
        raise ControlError("state_too_large", "状态超过读取上限")
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


@contextmanager
def workspace_lease(layout: RuntimeLayout):
    marker = layout.checked(layout.root / ".launcher-workspace")
    if not marker.is_file() or marker.read_text(encoding="utf-8") != "next-trainer-desktop-v1":
        raise ControlError("unowned_workspace", "只可修改正式启动器工作区")
    lock_path = layout.checked(layout.root / ".launcher-lock")
    with lock_path.open("a+b") as lock:
        try:
            if os.name == "nt":
                import msvcrt
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ControlError("workspace_busy", "工作区由另一个变更或训练进程使用") from error
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)

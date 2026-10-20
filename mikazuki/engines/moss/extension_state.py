"""Honest runtime states and content drift detection, without GUI ML imports."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import uuid

from .manifest import UPSTREAM
from .settings import REQUIRED_SOURCE_FILES, feature_enabled

FINGERPRINT_SCHEME = "moss-content-v1"
VALID_STATES = {"not_installed", "installing", "auditing", "ready", "broken", "disabled"}
_recovery_lock = threading.Lock()
_fingerprint_cache: dict[str, tuple[float, int, str]] = {}
_FINGERPRINT_TTL_SEC = 5.0


def write_state(runtime, state, facts=None, reason=""):
    _fingerprint_cache.pop(str(runtime.root), None)
    runtime.root.mkdir(parents=True, exist_ok=True)
    temporary = runtime.state_file.with_suffix(f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps({"state": state, "facts": facts or {}, "reason": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(runtime.state_file)


def source_commit(runtime):
    dot_git = runtime.source / ".git"
    try:
        if dot_git.is_file():
            gitdir = dot_git.read_text(encoding="utf-8").strip()
            if gitdir.startswith("gitdir:"):
                dot_git = (runtime.source / gitdir.split(":", 1)[1].strip()).resolve()
        head_file = dot_git / "HEAD"
        if head_file.is_file():
            head = head_file.read_text(encoding="utf-8").strip()
            if not head.startswith("ref:"):
                return head
            ref_file = dot_git / head.split(":", 1)[1].strip()
            if ref_file.is_file():
                return ref_file.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    try:
        result = subprocess.run(["git", "-C", str(runtime.source), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=15)
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _venv_metadata_files(venv):
    found = set()
    for base in (
        "Lib/site-packages",
        "Lib/site-packages/setuptools/_vendor",
        "lib/python*/site-packages",
        "lib/python*/site-packages/setuptools/_vendor",
        "lib",
        ".",
    ):
        for suffix in ("*.dist-info/METADATA", "*.dist-info/direct_url.json", "*.pth"):
            found.update(venv.glob(f"{base}/{suffix}"))
    return found


def fingerprint(runtime):
    """Hash code/package metadata rather than mtimes or model weights."""
    files = {runtime.python, runtime.root / ".venv/pyvenv.cfg"}
    files.update(runtime.source / name for name in REQUIRED_SOURCE_FILES)
    for pattern in ("library/moss/**/*.py", "library/runtime/**/*.py", "scripts/moss/**/*.py"):
        files.update(runtime.source.glob(pattern))
    files.update(_venv_metadata_files(runtime.root / ".venv"))
    entries = []
    for path in sorted(files):
        identity = path.relative_to(runtime.root).as_posix()
        if path.is_symlink():
            entries.append([identity, "symlink", os.readlink(path)])
        elif path.is_file():
            entries.append([identity, "sha256", hashlib.sha256(path.read_bytes()).hexdigest()])
        else:
            entries.append([identity, "missing"])
    raw = json.dumps([FINGERPRINT_SCHEME, source_commit(runtime), entries]).encode()
    return hashlib.sha256(raw).hexdigest()


def fingerprint_facts(runtime):
    return {"fingerprint": fingerprint(runtime), "fingerprint_scheme": FINGERPRINT_SCHEME}


def _complete(runtime):
    return runtime.python.is_file() and all((runtime.source / name).is_file() for name in REQUIRED_SOURCE_FILES)


def _recover(runtime, audit_fn):
    if not any(path.exists() for path in (runtime.source, runtime.root / ".venv", runtime.python_install_dir)):
        return {"state": "not_installed", "facts": {}, "reason": ""}
    if not _complete(runtime):
        return {"state": "broken", "facts": {}, "reason": "MOSS 源码或独立 Python 不完整，请修复环境。"}
    audit = audit_fn(runtime)
    facts = {"recovery": "missing_install_state", "audit": audit, "source_commit": UPSTREAM["commit"]}
    state, reason = "broken", "; ".join(audit.get("errors") or ["MOSS 环境审计失败。"])
    if audit.get("ok"):
        facts.update(fingerprint_facts(runtime))
        state, reason = "ready", "状态文件缺失，已重新审计实体环境。"
    write_state(runtime, state, facts, reason)
    return {"state": state, "facts": facts, "reason": reason}


def _cached_fingerprint(runtime):
    import time
    key = str(runtime.root)
    try:
        state_mtime = runtime.state_file.stat().st_mtime_ns
    except OSError:
        state_mtime = 0
    hit = _fingerprint_cache.get(key)
    now = time.monotonic()
    if hit and hit[1] == state_mtime and (now - hit[0]) < _FINGERPRINT_TTL_SEC:
        return hit[2]
    value = fingerprint(runtime)
    _fingerprint_cache[key] = (now, state_mtime, value)
    return value


def read_status(runtime, *, audit_fn=None):
    from .environment import audit_environment

    try:
        with _recovery_lock:
            if runtime.state_file.exists():
                data = json.loads(runtime.state_file.read_text(encoding="utf-8"))
                if not isinstance(data, dict) or not isinstance(data.get("facts"), dict) or data.get("state") not in VALID_STATES:
                    raise ValueError("invalid state shape")
            else:
                data = _recover(runtime, audit_fn or audit_environment)
    except (OSError, ValueError, TypeError) as exc:
        data = {"state": "broken", "facts": {}, "reason": f"MOSS 安装状态损坏，请修复：{exc}"}
    if data["state"] in {"installing", "auditing"}:
        from mikazuki.tasks import tm, TaskStatus

        task = tm.tasks.get(data["facts"].get("task_id"))
        if task is None or task.status not in {TaskStatus.CREATED, TaskStatus.QUEUED, TaskStatus.RUNNING}:
            data.update(state="broken", reason="MOSS 安装已中断，请重新安装或修复。")
    if data["state"] == "ready":
        facts = data["facts"]
        if not _complete(runtime):
            data.update(state="broken", reason="MOSS 源码或独立 Python 缺失，请修复环境。")
        elif not isinstance(facts.get("audit"), dict) or not facts["audit"].get("ok") or facts.get("source_commit") != UPSTREAM["commit"]:
            data.update(state="broken", reason="MOSS 缺少当前版本的成功审计，请修复环境。")
        else:
            try:
                if facts.get("fingerprint_scheme") != FINGERPRINT_SCHEME or facts.get("fingerprint") != _cached_fingerprint(runtime):
                    data.update(state="broken", reason="MOSS 环境或源码已变化，请修复后重新检查。")
            except OSError as exc:
                data.update(state="broken", reason=f"MOSS 环境文件无法读取，请修复：{exc}")
    data["feature_enabled"] = feature_enabled()
    if not data["feature_enabled"]:
        data["state"] = "disabled"
    data["runtime"] = {"python": str(runtime.python), "environment_path": str(runtime.root), "source": str(runtime.source)}
    return data


def check_runtime(runtime):
    """Train-time gate rechecks imports/GPU; a prior ready badge is not enough."""
    from .environment import audit_environment

    status = read_status(runtime)
    if status["state"] != "ready":
        raise ValueError(status.get("reason") or "请先安装并启用 MOSS 训练环境。")
    audit = audit_environment(runtime)
    if not audit.get("ok"):
        reason = "; ".join(audit.get("errors") or ["MOSS 环境审计失败。"])
        write_state(runtime, "broken", {**status["facts"], "audit": audit}, reason)
        raise ValueError(reason)

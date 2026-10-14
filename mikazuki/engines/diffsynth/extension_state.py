import json
import hashlib
import os
import subprocess
import threading

from .manifest import UPSTREAM
from .settings import TRAIN_SCRIPT, feature_enabled


# Bumped whenever the ingredient list or hashing changes. A state file written
# with an older scheme is migrated once instead of being reported as broken.
FINGERPRINT_SCHEME = "content-v2"
# Files larger than this are pinned by size alone: hashing multi-GB weights on
# every status poll is wasteful, and those entries are never user-edited.
FINGERPRINT_MAX_HASH_BYTES = 8 * 1024 * 1024

# Serialize missing-state recovery so concurrent status polls only audit once.
_missing_state_lock = threading.Lock()


def write_state(runtime, state, facts=None, reason=""):
    runtime.root.mkdir(parents=True, exist_ok=True)
    temporary = runtime.state_file.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"state": state, "facts": facts or {}, "reason": reason}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(runtime.state_file)


def _fingerprint_entry(path, runtime):
    try:
        identity = path.relative_to(runtime.root).as_posix()
    except ValueError:
        identity = path.name
    if path.is_symlink():
        stat = path.lstat()
        return [identity, stat.st_size, "symlink", os.readlink(path)]
    stat = path.stat()
    if stat.st_size > FINGERPRINT_MAX_HASH_BYTES:
        return [identity, stat.st_size, "size", ""]
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return [identity, stat.st_size, "sha256", digest.hexdigest()]


def fingerprint(runtime):
    """Content-based fingerprint of the runtime (#410).

    Timestamps are excluded on purpose: cloud images, Docker layers, backups and
    plain directory copies rewrite mtimes without touching the environment, and a
    timestamp-only difference used to report a healthy install as broken, pushing
    users into a multi-GB repair. Content hashes still catch same-length edits.
    """
    files = [runtime.python, runtime.source / TRAIN_SCRIPT, runtime.source / "pyproject.toml"]
    files += sorted(runtime.source.glob("diffsynth/**/*.py"))
    files += sorted((runtime.root / ".venv").glob("**/*.dist-info/METADATA"))
    entries = []
    for path in files:
        if not path.is_file() and not path.is_symlink():
            continue
        entries.append(_fingerprint_entry(path, runtime))
    head = subprocess.run(
        ["git", "-C", str(runtime.source), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    return hashlib.sha256(json.dumps([FINGERPRINT_SCHEME, head, entries]).encode()).hexdigest()


def fingerprint_facts(runtime):
    """Facts to persist next to a ready state (hash + the scheme that produced it)."""
    return {"fingerprint": fingerprint(runtime), "fingerprint_scheme": FINGERPRINT_SCHEME}


def _extension_empty(runtime) -> bool:
    if not runtime.root.exists():
        return True
    try:
        next(runtime.root.iterdir())
    except StopIteration:
        return True
    return False


def _has_runtime_markers(runtime) -> bool:
    return (
        (runtime.root / ".venv").exists()
        or runtime.python_install_dir.exists()
        or runtime.source.exists()
    )


def _runtime_entry_complete(runtime) -> bool:
    return runtime.python.is_file() and (runtime.source / TRAIN_SCRIPT).is_file()


def recover_missing_state(runtime, *, audit_fn=None):
    """Infer status when ``install_state.json`` is gone but a runtime may remain (#459).

    Cloud images / migrations often ship ``.python`` / ``.venv`` / ``source`` without
    the state file. Blindly returning ``not_installed`` pushes users into a multi-GB
    reinstall. When the structural entry points exist, audit once and persist.
    """
    if _extension_empty(runtime):
        return {"state": "not_installed", "facts": {}, "reason": ""}

    if not _runtime_entry_complete(runtime):
        if _has_runtime_markers(runtime):
            return {
                "state": "broken",
                "facts": {},
                "reason": "环境不完整（缺少独立 Python 或训练入口），请修复 DiffSynth 环境。",
            }
        return {"state": "not_installed", "facts": {}, "reason": ""}

    from .environment import audit_environment

    audit = (audit_fn or audit_environment)(runtime)
    facts = {"recovery": "missing_install_state", "audit": audit}
    if not audit.get("ok"):
        reason = "; ".join(audit.get("errors") or ["环境审计失败"])
        write_state(runtime, "broken", facts, reason)
        return {"state": "broken", "facts": facts, "reason": reason}

    facts = {
        **facts,
        "source_commit": UPSTREAM["commit"],
        **fingerprint_facts(runtime),
    }
    reason = "状态文件缺失，已根据实体环境自动恢复"
    write_state(runtime, "ready", facts, reason)
    return {"state": "ready", "facts": facts, "reason": reason}


def _load_or_recover_state(runtime, *, audit_fn=None):
    if runtime.state_file.exists():
        return json.loads(runtime.state_file.read_text(encoding="utf-8"))
    with _missing_state_lock:
        if runtime.state_file.exists():
            return json.loads(runtime.state_file.read_text(encoding="utf-8"))
        return recover_missing_state(runtime, audit_fn=audit_fn)


def read_status(runtime, *, audit_fn=None):
    data = _load_or_recover_state(runtime, audit_fn=audit_fn)
    if data["state"] in {"installing", "auditing"}:
        from mikazuki.tasks import tm, TaskStatus

        task = tm.tasks.get(data["facts"].get("task_id"))
        if task is None or task.status in {TaskStatus.FAILED, TaskStatus.TERMINATED, TaskStatus.FINISHED}:
            data.update(state="broken", reason="安装中断，请修复 DiffSynth 环境。")
    if data["state"] == "ready" and not _runtime_entry_complete(runtime):
        data.update(state="broken", reason="训练入口或独立 Python 缺失，请修复环境。")
    if data["state"] == "ready":
        stored = data["facts"].get("fingerprint")
        current = fingerprint(runtime)
        if stored is None or data["facts"].get("fingerprint_scheme") != FINGERPRINT_SCHEME:
            # Legacy state (no scheme / size+mtime hash): its hash cannot be compared
            # with the content scheme, and the mtime rewrites this issue is about are
            # exactly what produced a false mismatch. The runtime is present (checked
            # above), so refresh once instead of sending the user into a reinstall.
            data["facts"].update({"fingerprint": current, "fingerprint_scheme": FINGERPRINT_SCHEME})
            write_state(runtime, "ready", data["facts"], data.get("reason", ""))
        elif stored != current:
            data.update(state="broken", reason="环境或源码已变化，请修复后重新检查。")
    data["feature_enabled"] = feature_enabled()
    if not data["feature_enabled"]:
        data["state"] = "disabled"
    data["runtime"] = {
        "python": str(runtime.python),
        "environment_path": str(runtime.root),
        "source": str(runtime.source),
    }
    return data

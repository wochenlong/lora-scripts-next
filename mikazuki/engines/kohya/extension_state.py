import hashlib
import json
import os
import threading
import time

from .environment import (
    TORCH_PINS,
    TORCH_PINS_AARCH64,
    TRAINING_DEPS,
    audit_python,
    compute_drift,
)
from .settings import main_env_python_candidates

FINGERPRINT_SCHEME = "content-v1"
FINGERPRINT_MAX_HASH_BYTES = 8 * 1024 * 1024
_recovery_lock = threading.Lock()


def write_state(runtime, state, facts=None, reason=""):
    runtime.root.mkdir(parents=True, exist_ok=True)
    temporary = runtime.state_file.with_suffix(".tmp")
    temporary.write_text(json.dumps({"state": state, "facts": facts or {}, "reason": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(runtime.state_file)


def fingerprint(runtime):
    # The training source ships with the repository and updates via git pull;
    # only the venv content and the pinned dependency set gate readiness.
    files = [runtime.python]
    files += sorted((runtime.root / ".venv").glob("**/*.dist-info/METADATA"))
    entries = []
    for path in files:
        if not path.is_file() and not path.is_symlink():
            continue
        try:
            identity = path.relative_to(runtime.root).as_posix()
        except ValueError:
            identity = path.name
        if path.is_symlink():
            entries.append((identity, path.lstat().st_size, "symlink", os.readlink(path)))
            continue
        stat = path.stat()
        if stat.st_size > FINGERPRINT_MAX_HASH_BYTES:
            entries.append((identity, stat.st_size, "size", ""))
            continue
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        entries.append((identity, stat.st_size, "sha256", digest.hexdigest()))
    pins = [*TRAINING_DEPS, *TORCH_PINS, *TORCH_PINS_AARCH64]
    return hashlib.sha256(json.dumps([FINGERPRINT_SCHEME, pins, entries]).encode()).hexdigest()


def fingerprint_facts(runtime):
    return {"fingerprint": fingerprint(runtime), "fingerprint_scheme": FINGERPRINT_SCHEME}


# Main-env audits spawn a python subprocess importing torch (seconds), so
# results are cached in-process: successes forever, failures briefly so a
# fixed main env is picked up without requiring a GUI restart.
_MAIN_ENV_AUDIT_CACHE = {}
_MAIN_ENV_FAILURE_TTL = 120.0


def audit_main_env_python(python):
    """Match the training launcher's user-site policy (process.py
    _should_disable_user_site): audit isolated first; only when that fails,
    retry with user site enabled for pip --user style installs. Enabling user
    site unconditionally would let ~/.local packages shadow the env's own
    stack and break otherwise healthy environments.
    """
    payload = audit_python(python)
    if not payload.get("ok"):
        retry = audit_python(python, allow_user_site=True)
        if retry.get("ok"):
            return retry
    return payload


def _cached_main_env_audit(python):
    key = str(python)
    hit = _MAIN_ENV_AUDIT_CACHE.get(key)
    if hit:
        ok, payload, cached_at = hit
        if ok or time.monotonic() - cached_at < _MAIN_ENV_FAILURE_TTL:
            return payload
    payload = audit_main_env_python(python)
    _MAIN_ENV_AUDIT_CACHE[key] = (bool(payload.get("ok")), payload, time.monotonic())
    return payload


def _main_env_fallback(runtime, standalone_state):
    """Legacy forward compatibility: pre-standalone releases trained in the
    main environment (portable ``python_embeded`` or the GUI interpreter). If
    that environment already passes the training audit, report ready instead
    of forcing a multi-GB reinstall into ``extensions/kohya``.

    Returns ``(ready_payload, None)`` when a candidate passes, otherwise
    ``(None, diagnostics)`` with the last rejection for support visibility.
    """

    standalone_python = None
    try:
        standalone_python = str(runtime.python.resolve())
    except OSError:
        pass
    last_failure = None
    for python in main_env_python_candidates(runtime.project_root):
        try:
            if str(python.resolve()) == standalone_python:
                continue
        except OSError:
            pass
        audit = _cached_main_env_audit(python)
        if audit.get("ok"):
            drift = compute_drift(audit.get("versions") or {})
            facts = {
                "mode": "main_env",
                "main_env_python": str(python),
                "audit": audit,
                "standalone_state": standalone_state,
                "update_available": bool(drift),
            }
            if drift:
                facts["drift"] = drift
            return {
                "state": "ready",
                "facts": facts,
                "reason": "",
                "feature_enabled": True,
                "runtime": {"python": str(python), "environment_path": str(runtime.root)},
            }, None
        last_failure = {"python": str(python), "errors": audit.get("errors", [])}
    diagnostics = {"main_env_rejected": last_failure} if last_failure else None
    return None, diagnostics


def installed_versions_from_venv(runtime):
    """Installed package versions of the standalone venv, parsed from
    dist-info METADATA (no subprocess, safe to call on status polls)."""
    from packaging.utils import canonicalize_name

    versions = {}
    for metadata in (runtime.root / ".venv").glob("**/*.dist-info/METADATA"):
        name = version = None
        try:
            with open(metadata, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if line.startswith("Name: "):
                        name = line[6:].strip()
                    elif line.startswith("Version: "):
                        version = line[9:].strip()
                    if name and version:
                        break
                    if line.strip() == "":
                        break
        except OSError:
            continue
        if name and version:
            versions[canonicalize_name(name)] = version
    return versions


def invalidate_main_env_audit_cache():
    _MAIN_ENV_AUDIT_CACHE.clear()


# In-memory marker for an in-flight main-env incremental upgrade; the main env
# has no state file of its own and must not touch the standalone one.
_ACTIVE_MAIN_ENV_UPGRADE = None


def note_main_env_upgrade(python, task_id):
    global _ACTIVE_MAIN_ENV_UPGRADE
    _ACTIVE_MAIN_ENV_UPGRADE = {"python": str(python), "task_id": task_id}


def _main_env_upgrade_status(runtime):
    global _ACTIVE_MAIN_ENV_UPGRADE
    if not _ACTIVE_MAIN_ENV_UPGRADE:
        return None
    from mikazuki.tasks import TaskStatus, tm
    task = tm.tasks.get(_ACTIVE_MAIN_ENV_UPGRADE["task_id"])
    if task is not None and task.status not in {TaskStatus.FAILED, TaskStatus.TERMINATED, TaskStatus.FINISHED}:
        return {
            "state": "installing",
            "facts": {"task_id": _ACTIVE_MAIN_ENV_UPGRADE["task_id"], "mode": "main_env", "upgrade": True},
            "reason": "",
            "feature_enabled": True,
            "runtime": {"python": _ACTIVE_MAIN_ENV_UPGRADE["python"], "environment_path": str(runtime.root)},
        }
    invalidate_main_env_audit_cache()
    _ACTIVE_MAIN_ENV_UPGRADE = None
    return None


def _recover_missing_state(runtime, audit_fn):
    if not any(path.exists() for path in (runtime.root / ".venv", runtime.python_install_dir)):
        return {"state": "not_installed", "facts": {}}
    if not runtime.python.is_file():
        return {"state": "broken", "facts": {}, "reason": "独立 Python 缺失，请修复环境。"}
    audit = audit_fn(runtime)
    facts = {"recovery": "missing_install_state", "audit": audit}
    if not audit.get("ok"):
        reason = "; ".join(audit.get("errors") or ["Kohya 环境审计失败。"])
        write_state(runtime, "broken", facts, reason)
        return {"state": "broken", "facts": facts, "reason": reason}
    facts.update(fingerprint_facts(runtime))
    reason = "状态文件缺失，已根据实体环境自动恢复。"
    write_state(runtime, "ready", facts, reason)
    return {"state": "ready", "facts": facts, "reason": reason}


def read_status(runtime, *, audit_fn=None):
    upgrading = _main_env_upgrade_status(runtime)
    if upgrading is not None:
        return upgrading
    if runtime.state_file.exists():
        data = json.loads(runtime.state_file.read_text(encoding="utf-8"))
    else:
        with _recovery_lock:
            if runtime.state_file.exists():
                data = json.loads(runtime.state_file.read_text(encoding="utf-8"))
            else:
                from .environment import audit_environment
                data = _recover_missing_state(runtime, audit_fn or audit_environment)
    if data["state"] in {"installing", "auditing"}:
        from mikazuki.tasks import TaskStatus, tm
        task = tm.tasks.get(data["facts"].get("task_id"))
        if task is None or task.status in {TaskStatus.FAILED, TaskStatus.TERMINATED, TaskStatus.FINISHED}:
            invalidate_main_env_audit_cache()
            data.update(state="broken", reason="安装中断，请修复 kohya 环境。")
    if data["state"] == "ready" and not runtime.python.is_file():
        data.update(state="broken", reason="独立 Python 缺失，请修复环境。")
    if data["state"] == "ready":
        if data["facts"].get("fingerprint_scheme") != FINGERPRINT_SCHEME:
            from .environment import audit_environment
            audit = (audit_fn or audit_environment)(runtime)
            data["facts"]["audit"] = audit
            if not audit.get("ok"):
                data.update(state="broken", reason="; ".join(audit.get("errors") or ["Kohya 环境审计失败。"]))
            else:
                data["facts"].update(fingerprint_facts(runtime))
                write_state(runtime, "ready", data["facts"], "旧版环境状态已通过审计并迁移。")
        elif data["facts"].get("fingerprint") != fingerprint(runtime):
            data.update(state="broken", reason="环境已变化，请修复后重新检查。")
    if data["state"] == "ready":
        # Pin drift never blocks: the env was audited ready at install time,
        # so a mismatch with the current pins only means an upgrade is advised.
        drift = compute_drift(installed_versions_from_venv(runtime))
        data["facts"]["mode"] = "standalone"
        data["facts"]["update_available"] = bool(drift)
        if drift:
            data["facts"]["drift"] = drift
        data["feature_enabled"] = True
        data["runtime"] = {"python": str(runtime.python), "environment_path": str(runtime.root)}
        return data
    if data["state"] in {"not_installed", "broken"}:
        fallback, diagnostics = _main_env_fallback(runtime, data["state"])
        if fallback is not None:
            return fallback
        if diagnostics:
            data["facts"] = {**data.get("facts", {}), **diagnostics}
    data["feature_enabled"] = True
    data["runtime"] = {"python": str(runtime.python), "environment_path": str(runtime.root)}
    return data

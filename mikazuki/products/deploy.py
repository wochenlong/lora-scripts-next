"""Declarative deploy of products to inference-platform model directories.

The registry stores the *desired* state (``deployed_to`` per target).
Reconciliation compares desire with reality:

- desired=deployed, target file missing        -> copy/link it back
- desired=removed,  target file still present  -> remove it
- same-name file with a different hash         -> conflict, never
  overwrite or delete; surfaced to the UI instead

Links (symlinks) fall back to copying when the platform disallows them
(Windows without developer mode / admin).
"""

import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from mikazuki.log import log

from .registry import Registry, product_id_for_path

DEPLOY_DESIRED = "deployed"
DEPLOY_REMOVED = "removed"


def default_targets_path() -> Path:
    return Path(os.getcwd()) / "config" / "products" / "deploy_targets.json"


def load_targets(path: Optional[Path] = None) -> Dict[str, str]:
    """{name: absolute directory} mapping; missing/corrupt file -> empty."""
    p = Path(path) if path else default_targets_path()
    try:
        raw = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    targets: Dict[str, str] = {}
    for item in raw.get("targets", []):
        name, directory = item.get("name"), item.get("path")
        if name and directory:
            targets[str(name)] = str(Path(directory).resolve())
    return targets


def save_targets(targets: Dict[str, str], path: Optional[Path] = None) -> None:
    p = Path(path) if path else default_targets_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"targets": [{"name": k, "path": v} for k, v in sorted(targets.items())]}
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def file_sha1(path: Path, _chunk: int = 1 << 20) -> str:
    digest = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(_chunk)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def quick_same(path: Path, size: Optional[int], mtime: Optional[float]) -> bool:
    try:
        stat = path.stat()
    except OSError:
        return False
    return size is not None and stat.st_size == size and mtime is not None and abs(stat.st_mtime - mtime) < 1


def _place(source: Path, target: Path, method: str) -> str:
    """Copy or link source -> target; returns the method actually used."""
    if method == "link":
        try:
            target.symlink_to(source)
            return "link"
        except OSError as exc:
            log.info(f"symlink failed ({exc}); falling back to copy")
    shutil.copy2(source, target)
    return "copy"


def deploy_product(registry: Registry, *, product_path: str, product_family: str,
                   target_name: str, target_dir: str, method: str = "copy") -> dict:
    """Deploy one product file into a target directory and record desired state."""
    source = Path(product_path)
    if not source.is_file():
        raise FileNotFoundError(f"制品文件不存在: {product_path}")
    target_directory = Path(target_dir)
    target_directory.mkdir(parents=True, exist_ok=True)
    target = target_directory / source.name

    pid = product_id_for_path(source)
    if target.exists() or target.is_symlink():
        recorded = registry.get_product_state(pid).get("deployed_to", {}).get(target_name)
        if recorded and quick_same(target, recorded.get("size"), recorded.get("mtime")):
            return {"target": target_name, "path": str(target), "status": "already"}
        if recorded and file_sha1(target) == recorded.get("sha1"):
            return {"target": target_name, "path": str(target), "status": "already"}
        raise FileExistsError(f"目标目录已存在同名不同内容的文件: {target}")

    used = _place(source, target, method)
    stat = target.stat()
    deployed_to = dict(registry.get_product_state(pid).get("deployed_to") or {})
    deployed_to[target_name] = {
        "path": str(target.resolve()),
        "desired": DEPLOY_DESIRED,
        "method": used,
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "sha1": file_sha1(target),
        "deployed_at": datetime.now().timestamp(),
    }
    registry.update_product_state(
        pid, path=str(source.resolve()), family=product_family, deployed_to=deployed_to,
    )
    return {"target": target_name, "path": str(target), "status": "deployed", "method": used}


def undeploy_product(registry: Registry, *, product_path: str, target_name: str) -> dict:
    """Mark a deployment as removed and reconcile immediately."""
    pid = product_id_for_path(product_path)
    state = registry.get_product_state(pid)
    deployed_to = dict(state.get("deployed_to") or {})
    entry = deployed_to.get(target_name)
    if not entry:
        return {"target": target_name, "status": "not_deployed"}
    entry["desired"] = DEPLOY_REMOVED
    deployed_to[target_name] = entry
    registry.update_product_state(pid, path=product_path, deployed_to=deployed_to)
    return {"target": target_name, **reconcile_entry(entry)}


def check_entry(entry: dict) -> dict:
    """Read-only deployment status for one entry. Never mutates the fs."""
    target = Path(entry["path"])
    desired = entry.get("desired", DEPLOY_DESIRED)
    exists = target.exists() or target.is_symlink()

    if desired == DEPLOY_REMOVED:
        if not exists:
            return {"status": "removed"}
        if quick_same(target, entry.get("size"), entry.get("mtime")) or file_sha1(target) == entry.get("sha1"):
            return {"status": "pending_removal"}
        return {"status": "conflict", "message": "对面存在同名但内容不同的文件，未删除"}

    # desired == deployed
    if exists:
        if quick_same(target, entry.get("size"), entry.get("mtime")):
            return {"status": "ok"}
        if file_sha1(target) == entry.get("sha1"):
            return {"status": "ok"}
        return {"status": "conflict", "message": "对面存在同名但内容不同的文件，未覆盖"}
    return {"status": "missing"}


def reconcile_entry(entry: dict) -> dict:
    """Apply one deployed_to entry to the filesystem. Never touches files whose
    content differs from what we deployed (conflict)."""
    outcome = check_entry(entry)
    if outcome["status"] != "pending_removal":
        return outcome
    try:
        Path(entry["path"]).unlink()
    except OSError as exc:
        return {"status": "error", "message": str(exc)}
    return {"status": "removed"}


def restore_entry(entry: dict, source: Path) -> dict:
    """Re-deploy a desired=deployed entry whose target file disappeared."""
    if not source.is_file():
        return {"status": "error", "message": f"源文件不存在: {source}"}
    target = Path(entry["path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    used = _place(source, target, entry.get("method", "copy"))
    stat = target.stat()
    entry.update({"method": used, "size": stat.st_size, "mtime": stat.st_mtime,
                  "sha1": file_sha1(target)})
    return {"status": "restored", "method": used}


def reconcile_all(registry: Registry, targets: Dict[str, str]) -> List[dict]:
    """Reconcile every tracked deployment; returns per-entry results."""
    results: List[dict] = []
    for pid, state in registry.product_states.items():
        source_path = state.get("path")
        deployed_to = dict(state.get("deployed_to") or {})
        changed = False
        for target_name, entry in list(deployed_to.items()):
            if target_name not in targets:
                continue
            outcome = reconcile_entry(entry)
            if outcome["status"] == "missing" and entry.get("desired") == DEPLOY_DESIRED and source_path:
                outcome = restore_entry(entry, Path(source_path))
                changed = True
            if outcome["status"] == "removed" and entry.get("desired") == DEPLOY_REMOVED:
                del deployed_to[target_name]
                changed = True
            results.append({"id": pid, "target": target_name, **outcome})
        if changed:
            registry.update_product_state(pid, path=source_path, deployed_to=deployed_to)
    return results

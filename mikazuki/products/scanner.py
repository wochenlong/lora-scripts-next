"""Filesystem scanner for training products (.safetensors model files).

Scanning is user-triggered (never automatic): enumerate model files under
the given directories, read only the safetensors header (millisecond-level)
and fold the results together with the registry (runs, lineage, deploy
state). Products whose files disappear are reported as ``missing`` — the
registry never drops records on its own (no lifecycle hosting).
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from mikazuki.log import log
from mikazuki.utils.train_utils import read_safetensors_metadata

from .registry import Registry, product_id_for_path

MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".pt"}

# kohya epoch saves:  ``name-000001.safetensors``
# kohya step saves:   ``name-step000001.safetensors`` / ``name-000001-step000100``
_EPOCH_RE = re.compile(r"^(?P<base>.+?)-(?P<epoch>\d{6})$")
_STEP_RE = re.compile(r"^(?P<base>.+?)(?:-(?P<epoch>\d{6}))?-step(?P<step>\d+)$")


def resolve_output_path(path: Optional[str], cwd: Optional[Path] = None) -> Optional[str]:
    """Resolve a (possibly relative) configured path against the server cwd.

    This is the F5a "location transparency" rule: users see the absolute
    path the training backend will actually write to.
    """
    if not path:
        return None
    base = Path(cwd) if cwd else Path.cwd()
    return str((base / path).resolve()) if not os.path.isabs(path) else str(Path(path).resolve())


def classify_family(metadata: Dict) -> str:
    """Best-effort model family from ss_* metadata, used for tab paging."""
    meta = metadata or {}
    module = str(meta.get("ss_network_module") or "").lower()
    base_version = str(meta.get("ss_base_model_version") or "").lower()
    model_name = str(meta.get("ss_sd_model_name") or "").lower()
    haystack = f"{module} {base_version} {model_name}"

    if "flux" in haystack:
        return "flux"
    if "sd3" in haystack or "anima" in haystack or "sd3.5" in haystack:
        return "sd3"
    if "xl" in base_version or "sdxl" in haystack:
        return "sdxl"
    if base_version or module:
        return "sd"
    return "other"


def is_lycoris_like(metadata: Dict) -> bool:
    """LoKr/LoHA etc. are Kronecker/other decompositions: no lora_down/up."""
    module = str((metadata or {}).get("ss_network_module") or "").lower()
    return "lycoris" in module or "lokr" in module or "loha" in module


def split_epoch_stem(stem: str) -> Tuple[str, Optional[int], Optional[int]]:
    """Split a file stem into (group base, epoch, step)."""
    m = _STEP_RE.match(stem)
    if m:
        epoch = int(m.group("epoch")) if m.group("epoch") else None
        return m.group("base"), epoch, int(m.group("step"))
    m = _EPOCH_RE.match(stem)
    if m:
        return m.group("base"), int(m.group("epoch")), None
    return stem, None, None


def summarize_product(path: Path, metadata: Optional[Dict] = None) -> dict:
    """Build the list-row summary for one product file (header-only read)."""
    stat = path.stat()
    if metadata is None:
        try:
            header = read_safetensors_metadata(str(path)) or {}
        except Exception as exc:  # noqa: BLE001 - unreadable file must not break listing
            log.warning(f"Failed to read safetensors header for {path}: {exc}")
            header = {}
        metadata = header.get("__metadata__", {}) if isinstance(header, dict) else {}

    base, epoch, step = split_epoch_stem(path.stem)
    return {
        "id": product_id_for_path(path),
        "name": path.name,
        "path": str(path.resolve()),
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "group_key": base,
        "epoch": epoch,
        "step": step,
        "dim": _to_int(metadata.get("ss_network_dim")),
        "alpha": _to_float(metadata.get("ss_network_alpha")),
        "base_model_version": metadata.get("ss_base_model_version"),
        "sd_model_name": metadata.get("ss_sd_model_name"),
        "network_module": metadata.get("ss_network_module"),
        "family": classify_family(metadata),
        "is_lycoris": is_lycoris_like(metadata),
    }


def _to_int(value) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _to_float(value) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def scan_directory(directory: Path) -> List[dict]:
    """Enumerate model files directly under a directory (non-recursive)."""
    products: List[dict] = []
    if not directory.is_dir():
        return products
    try:
        entries = sorted(directory.iterdir())
    except OSError as exc:
        log.warning(f"Cannot scan product directory {directory}: {exc}")
        return products
    for entry in entries:
        if entry.is_file() and entry.suffix.lower() in MODEL_EXTENSIONS:
            try:
                products.append(summarize_product(entry))
            except OSError as exc:
                log.warning(f"Cannot stat product file {entry}: {exc}")
    return products


def known_scan_dirs(registry: Registry) -> List[str]:
    """Union of run output_dirs + user-added scan dirs + default ./output."""
    dirs: List[str] = []

    def _add(path: Optional[str]) -> None:
        if path and path not in dirs:
            dirs.append(path)

    for run in registry.list_runs():
        _add(run.get("output_dir"))
    for path in registry.scan_dirs:
        _add(path)
    _add(str(Path("./output").resolve()))
    return dirs


def match_run(product: dict, runs: List[dict]) -> Optional[dict]:
    """Associate a product with a registered run by output_dir + name prefix."""
    product_dir = str(Path(product["path"]).parent)
    for run in runs:
        if run.get("output_dir") != product_dir:
            continue
        output_name = run.get("output_name")
        if output_name and product["group_key"] == Path(str(output_name)).stem:
            return run
        if output_name and product["group_key"].startswith(str(output_name)):
            return run
    return None


def collect_products(registry: Registry, extra_dirs: Optional[List[str]] = None) -> dict:
    """Full listing: scan known dirs, attach run/lineage/deploy state, group."""
    runs = registry.list_runs()
    dirs = known_scan_dirs(registry)
    if extra_dirs:
        for d in extra_dirs:
            resolved = str(Path(d).resolve())
            if resolved not in dirs:
                dirs.append(resolved)

    scanned_dirs: List[str] = []
    products: List[dict] = []
    seen_ids = set()
    for d in dirs:
        directory = Path(d)
        if not directory.is_dir():
            continue
        scanned_dirs.append(d)
        for product in scan_directory(directory):
            if product["id"] in seen_ids:
                continue
            seen_ids.add(product["id"])
            products.append(product)

    for product in products:
        run = match_run(product, runs)
        product["run_task_id"] = run["task_id"] if run else None
        product["train_type"] = run.get("train_type") if run else None
        state = registry.get_product_state(product["id"])
        product["derived_from"] = state.get("derived_from")
        product["deployed_to"] = state.get("deployed_to") or {}
        product["status"] = "present"

    # Registry products whose files disappeared: surface as missing.
    scanned_paths = {p["path"] for p in products}
    for pid, state in registry.product_states.items():
        path = state.get("path")
        if path and path not in scanned_paths and pid not in seen_ids:
            products.append({
                "id": pid,
                "name": Path(path).name,
                "path": path,
                "size": None,
                "mtime": None,
                "group_key": Path(path).stem,
                "epoch": None,
                "step": None,
                "dim": None,
                "alpha": None,
                "base_model_version": None,
                "sd_model_name": None,
                "network_module": None,
                "family": state.get("family") or "other",
                "is_lycoris": False,
                "run_task_id": None,
                "train_type": None,
                "derived_from": state.get("derived_from"),
                "deployed_to": state.get("deployed_to") or {},
                "status": "missing",
            })

    groups: Dict[str, dict] = {}
    for product in products:
        key = f'{product["group_key"]}@{str(Path(product["path"]).parent)}'
        group = groups.setdefault(key, {
            "key": key,
            "name": product["group_key"],
            "output_dir": str(Path(product["path"]).parent),
            "family": product["family"],
            "train_type": product["train_type"],
            "run_task_id": product["run_task_id"],
            "products": [],
        })
        group["products"].append(product)

    for group in groups.values():
        group["products"].sort(key=lambda p: (p["epoch"] is None, p["epoch"] or 0,
                                              p["step"] or 0, p["name"]))

    families = sorted({p["family"] for p in products})
    return {
        "groups": sorted(groups.values(), key=lambda g: max(
            (p["mtime"] or 0) for p in g["products"]), reverse=True),
        "families": families,
        "scanned_dirs": scanned_dirs,
    }

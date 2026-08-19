"""Append-only JSONL registry for training runs and products.

Design notes:
- One JSON op per line; state is folded from ops on load.
- Corrupted lines are skipped so a damaged registry never breaks training
  (degrades to plain file scanning).
- The file is compacted (rewritten as a minimal op set) once it grows past
  ``_COMPACT_THRESHOLD`` lines.
"""

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from mikazuki.log import log

_COMPACT_THRESHOLD = 1000


def default_registry_path() -> Path:
    return Path(os.getcwd()) / "config" / "products" / "registry.jsonl"


def product_id_for_path(path) -> str:
    """Stable product id: short hash of the normalized absolute path."""
    import hashlib

    normalized = os.path.normcase(str(Path(path).resolve()))
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


class Registry:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else default_registry_path()
        self._lock = threading.Lock()
        self.runs: Dict[str, dict] = {}
        self.scan_dirs: List[str] = []
        self.product_states: Dict[str, dict] = {}
        self._op_count = 0
        self.load()

    # ---- persistence ----

    def load(self) -> None:
        self.runs = {}
        self.scan_dirs = []
        self.product_states = {}
        self._op_count = 0
        if not self.path.is_file():
            return
        try:
            with open(self.path, "r", encoding="utf-8", errors="replace") as f:
                for lineno, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        op = json.loads(line)
                    except json.JSONDecodeError:
                        log.warning(f"Skipping corrupted registry line {lineno} in {self.path}")
                        continue
                    self._apply(op)
                    self._op_count += 1
        except OSError as exc:
            log.warning(f"Cannot read products registry {self.path}: {exc}")

    def _apply(self, op: dict) -> None:
        kind = op.get("op")
        if kind == "run":
            task_id = op.get("task_id")
            if task_id:
                self.runs[task_id] = {k: v for k, v in op.items() if k != "op"}
        elif kind == "scan_dir":
            path = op.get("path")
            if path and path not in self.scan_dirs:
                self.scan_dirs.append(path)
        elif kind == "product_state":
            pid = op.get("id")
            if pid:
                state = self.product_states.setdefault(pid, {})
                state.update({k: v for k, v in op.items() if k not in ("op", "id")})

    def _append(self, op: dict) -> None:
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.path, "a", encoding="utf-8", newline="\n") as f:
                    f.write(json.dumps(op, ensure_ascii=False) + "\n")
            except OSError as exc:
                log.warning(f"Cannot write products registry {self.path}: {exc}")
            self._apply(op)
            self._op_count += 1
            if self._op_count > _COMPACT_THRESHOLD:
                self._compact()

    def _compact(self) -> None:
        ops: List[dict] = []
        for run in self.runs.values():
            ops.append({"op": "run", **run})
        for path in self.scan_dirs:
            ops.append({"op": "scan_dir", "path": path})
        for pid, state in self.product_states.items():
            ops.append({"op": "product_state", "id": pid, **state})
        try:
            tmp = self.path.with_suffix(".jsonl.tmp")
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                for op in ops:
                    f.write(json.dumps(op, ensure_ascii=False) + "\n")
            os.replace(tmp, self.path)
            self._op_count = len(ops)
        except OSError as exc:
            log.warning(f"Cannot compact products registry {self.path}: {exc}")

    # ---- public API ----

    def record_run(self, *, task_id: str, train_type: str, config_path: str,
                   output_dir: Optional[str], output_name: Optional[str],
                   logging_dir: Optional[str] = None) -> None:
        def _abs(p):
            return str(Path(p).resolve()) if p else None

        self._append({
            "op": "run",
            "task_id": task_id,
            "registered_at": datetime.now().timestamp(),
            "train_type": train_type,
            "config_path": _abs(config_path),
            "output_dir": _abs(output_dir),
            "output_name": output_name or None,
            "logging_dir": _abs(logging_dir),
        })

    def add_scan_dir(self, path) -> str:
        resolved = str(Path(path).resolve())
        if resolved not in self.scan_dirs:
            self._append({"op": "scan_dir", "path": resolved})
        return resolved

    def update_product_state(self, product_id: str, **fields) -> None:
        """Merge fields into a product's user state (deployed_to, derived_from...)."""
        self._append({"op": "product_state", "id": product_id, **fields})

    def get_product_state(self, product_id: str) -> dict:
        return dict(self.product_states.get(product_id, {}))

    def list_runs(self) -> List[dict]:
        return sorted(self.runs.values(), key=lambda r: r.get("registered_at", 0), reverse=True)


_default_registry: Optional[Registry] = None
_default_registry_lock = threading.Lock()


def default_registry() -> Registry:
    global _default_registry
    with _default_registry_lock:
        if _default_registry is None:
            _default_registry = Registry()
        return _default_registry

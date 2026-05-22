"""Thread-safe tagger job progress for GET /api/tagger/status."""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass
class TaggerProgressSnapshot:
    active: bool = False
    phase: str = "idle"  # idle | preparing | download | tagging | done | error
    percent: Optional[float] = None
    current: int = 0
    total: int = 0
    label: str = ""
    message: str = ""


class TaggerProgress:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snap = TaggerProgressSnapshot()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return asdict(self._snap)

    def reset(self) -> None:
        with self._lock:
            self._snap = TaggerProgressSnapshot()

    def start_job(self) -> None:
        with self._lock:
            self._snap = TaggerProgressSnapshot(
                active=True,
                phase="preparing",
                message="准备中…",
            )

    def begin_download(self, model_name: str) -> None:
        with self._lock:
            if not self._snap.active:
                return
            self._snap.phase = "download"
            self._snap.label = model_name
            self._snap.percent = None
            self._snap.message = f"正在下载模型 · {model_name}"

    def end_download(self) -> None:
        with self._lock:
            if not self._snap.active or self._snap.phase != "download":
                return
            if self._snap.total > 0:
                self._snap.phase = "tagging"
                cur = self._snap.current
                total = self._snap.total
                self._snap.percent = (cur / total * 100.0) if total else None
                self._snap.message = f"{cur} / {total} · 正在打标"
            else:
                self._snap.phase = "preparing"
                self._snap.message = "准备中…"

    def begin_tagging(self, total: int) -> None:
        with self._lock:
            if not self._snap.active:
                return
            self._snap.phase = "tagging"
            self._snap.total = total
            self._snap.current = 0
            self._snap.percent = 0.0 if total else None
            self._snap.message = f"0 / {total} · 正在打标" if total else "正在打标"

    def update_tagging(self, current: int, total: int, filename: str) -> None:
        with self._lock:
            if not self._snap.active:
                return
            self._snap.phase = "tagging"
            self._snap.current = current
            self._snap.total = total
            self._snap.label = filename
            self._snap.percent = (current / total * 100.0) if total else None
            self._snap.message = f"{current} / {total} · 正在打标"

    def finish_ok(self, message: str = "识别完成") -> None:
        with self._lock:
            if not self._snap.active:
                return
            self._snap.phase = "done"
            self._snap.percent = 100.0
            self._snap.message = message

    def finish_error(self, message: str) -> None:
        with self._lock:
            self._snap.active = True
            self._snap.phase = "error"
            self._snap.percent = None
            self._snap.message = message


tagger_progress = TaggerProgress()

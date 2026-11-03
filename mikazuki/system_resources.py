"""Host GPU / RAM snapshot for the Tasks page header."""

from __future__ import annotations

from typing import Any

_nvml_ready: bool | None = None


def _ensure_nvml() -> bool:
    global _nvml_ready
    if _nvml_ready is not None:
        return _nvml_ready
    try:
        import pynvml

        pynvml.nvmlInit()
        _nvml_ready = True
    except Exception:
        _nvml_ready = False
    return _nvml_ready


def _gpu_snapshot() -> dict[str, Any] | None:
    if not _ensure_nvml():
        return None
    try:
        import pynvml

        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="replace")
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        return {
            "name": name,
            "vram_used_mb": int(round(mem.used / (1024 * 1024))),
            "vram_total_mb": int(round(mem.total / (1024 * 1024))),
            "gpu_load": int(util.gpu),
        }
    except Exception:
        return None


def _ram_snapshot() -> dict[str, Any] | None:
    try:
        import psutil

        mem = psutil.virtual_memory()
        return {
            "used_mb": int(round(mem.used / (1024 * 1024))),
            "total_mb": int(round(mem.total / (1024 * 1024))),
            "percent": float(mem.percent),
        }
    except Exception:
        return None


def collect_resources() -> dict[str, Any]:
    return {"gpu": _gpu_snapshot(), "ram": _ram_snapshot()}

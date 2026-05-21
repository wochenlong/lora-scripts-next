# -*- coding: utf-8 -*-
"""Helpers for portable Python and optional Flash Attention 2 support."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from typing import Callable, Dict, Optional, Tuple


FLASH_ATTN_WHEEL_VERSION = "2.7.4.post1"
FLASH_ATTN_CUDA_TAG = "cu128"
FLASH_ATTN_TORCH_VERSION = "2.7.0"
TRITON_WINDOWS_SPEC = "triton-windows<3.4"
FLASH_ATTN_WHEEL_BASE = "flash_attn-2.7.4.post1+cu128torch2.7.0cxx11abiFALSE"
FLASH_ATTN_WHEEL_HOSTS = {
    "global": "https://huggingface.co/lldacing/flash-attention-windows-wheel/resolve/main",
    "china": "https://hf-mirror.com/lldacing/flash-attention-windows-wheel/resolve/main",
}


def is_embedded_python(executable: Optional[str] = None) -> bool:
    exe = (executable or sys.executable).replace("\\", "/").lower()
    return "python_embeded" in exe or "python_embedded" in exe


def flash_attn_wheel_name(python_tag: Optional[str] = None) -> str:
    tag = python_tag or f"cp{sys.version_info.major}{sys.version_info.minor}"
    return f"{FLASH_ATTN_WHEEL_BASE}-{tag}-{tag}-win_amd64.whl"


def flash_attn_wheel_url(region: str = "global", python_tag: Optional[str] = None) -> str:
    host = FLASH_ATTN_WHEEL_HOSTS.get(region, FLASH_ATTN_WHEEL_HOSTS["global"])
    return f"{host}/{flash_attn_wheel_name(python_tag)}"


def flash_attn_probe() -> Tuple[bool, str]:
    """Return whether the flash-attn + Triton runtime can import cleanly."""
    try:
        import triton  # noqa: F401
        import flash_attn  # noqa: F401
        from flash_attn.ops.triton.rotary import apply_rotary  # noqa: F401
        return True, "flash-attn stack import OK"
    except Exception as exc:  # noqa: BLE001 - probe must never break startup
        return False, f"{exc.__class__.__name__}: {exc}"


def flash_attn_stack_usable() -> bool:
    """True only when flash-attn and its Triton ops import cleanly."""
    usable, _reason = flash_attn_probe()
    return usable


def sanitize_embedded_deps(log: Optional[Callable[[str], None]] = None) -> None:
    """Remove flash-attn / triton from embedded Python only when the stack cannot run."""
    if not is_embedded_python():
        return

    has_flash = importlib.util.find_spec("flash_attn") is not None
    has_triton = importlib.util.find_spec("triton") is not None
    if not has_flash and not has_triton:
        return

    usable, reason = flash_attn_probe()
    if has_flash and usable:
        if log:
            log("Portable package: flash-attn/Triton self-check passed; keeping Flash Attention 2 enabled.")
        return

    msg = (
        "Portable package: removing incompatible flash-attn/triton "
        f"(self-check failed: {reason}; training will use xformers or PyTorch SDPA)."
    )
    if log:
        log(msg)
    else:
        print(msg)

    subprocess.run(
        [
            sys.executable,
            "-s",
            "-m",
            "pip",
            "uninstall",
            "flash-attn",
            "flash_attn",
            "triton-windows",
            "triton",
            "-y",
        ],
        capture_output=True,
        timeout=120,
    )


def train_env_overrides() -> Dict[str, str]:
    """Environment for training subprocesses on embedded Python."""
    if not is_embedded_python():
        return {}
    if flash_attn_stack_usable():
        return {}
    return {"TRANSFORMERS_ATTN_IMPLEMENTATION": "sdpa"}

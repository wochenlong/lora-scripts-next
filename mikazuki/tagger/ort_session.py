"""Safe ONNX Runtime session creation for tagger models."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Callable


LogFn = Callable[[str], None]

# wd14-convnextv2-v2 ONNX is ~370–400 MB; smaller files are almost certainly broken downloads.
MIN_ONNX_BYTES = 50 * 1024 * 1024


def _log(message: str, log: LogFn | None = None) -> None:
    (log or print)(message)


def resolve_onnx_providers() -> list[str]:
    import onnxruntime as ort

    available = list(ort.get_available_providers())
    mode = (os.environ.get("MIKAZUKI_TAGGER_ORT_PROVIDERS") or "auto").strip().lower()

    if mode in {"cpu", "cpu_only", "cpu-only"}:
        return ["CPUExecutionProvider"] if "CPUExecutionProvider" in available else available

    if mode in {"cuda", "gpu"}:
        if "CUDAExecutionProvider" in available:
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]
        return ["CPUExecutionProvider"] if "CPUExecutionProvider" in available else available

    providers: list[str] = []
    if "CUDAExecutionProvider" in available:
        providers.append("CUDAExecutionProvider")
    if "CPUExecutionProvider" in available:
        providers.append("CPUExecutionProvider")
    return providers or available


def _validate_model_file(model_path: Path) -> None:
    if not model_path.is_file():
        raise FileNotFoundError(f"model file not found: {model_path}")
    size = model_path.stat().st_size
    if size < MIN_ONNX_BYTES:
        raise ValueError(
            f"model.onnx looks incomplete ({size} bytes, expected > {MIN_ONNX_BYTES // (1024 * 1024)} MB): "
            f"{model_path}. Re-download or repair the tagger model."
        )


def create_inference_session(model_path: os.PathLike | str, *, log: LogFn | None = None):
    from onnxruntime import InferenceSession, SessionOptions

    path = Path(model_path).resolve()
    _validate_model_file(path)
    _log(f"[tagger] Loading ONNX ({path.stat().st_size // (1024 * 1024)} MB): {path}", log)

    # CUDA EP may need torch-linked DLLs on Windows portable builds; torch is
    # optional now that training stacks live in engine venvs.
    try:
        import torch  # noqa: F401
    except ImportError:
        pass

    options = SessionOptions()
    options.log_severity_level = 3

    providers = resolve_onnx_providers()
    _log(f"[tagger] ONNX Runtime providers (requested): {providers}", log)

    timeout_s = int(os.environ.get("MIKAZUKI_TAGGER_ORT_LOAD_TIMEOUT", "180"))

    def _open_with(providers_to_use: list[str]):
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                InferenceSession,
                str(path),
                sess_options=options,
                providers=providers_to_use,
            )
            try:
                return future.result(timeout=timeout_s)
            except FuturesTimeoutError as exc:
                raise TimeoutError(
                    f"ONNX model load timed out after {timeout_s}s with providers {providers_to_use}. "
                    "Set MIKAZUKI_TAGGER_ORT_PROVIDERS=cpu to force CPU, or increase "
                    "MIKAZUKI_TAGGER_ORT_LOAD_TIMEOUT."
                ) from exc

    def _load_cpu_fallback(reason: BaseException):
        _log(f"[tagger] Retrying ONNX load with CPU only ({reason})", log)
        session = _open_with(["CPUExecutionProvider"])
        _log(f"[tagger] ONNX Runtime active providers: {session.get_providers()}", log)
        return session

    try:
        session = _open_with(providers)
        active = session.get_providers()
        _log(f"[tagger] ONNX Runtime active providers: {active}", log)
        return session
    except Exception as first_error:
        if "CUDAExecutionProvider" not in providers:
            raise
        return _load_cpu_fallback(first_error)

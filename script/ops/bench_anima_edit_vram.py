#!/usr/bin/env python3
"""Run 2-epoch Anima Edit VRAM bench (single vs dual @ 512) and record nvidia-smi peaks."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable


class GpuSampler:
    def __init__(self) -> None:
        self.peak_mib = 0
        self.samples: list[tuple[float, int]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _poll(self) -> None:
        while not self._stop.is_set():
            try:
                out = subprocess.check_output(
                    [
                        "nvidia-smi",
                        "--query-gpu=memory.used",
                        "--format=csv,noheader,nounits",
                    ],
                    text=True,
                    timeout=5,
                )
                mib = max(int(x.strip()) for x in out.strip().splitlines() if x.strip())
                self.peak_mib = max(self.peak_mib, mib)
                self.samples.append((time.time(), mib))
            except Exception:
                pass
            time.sleep(0.5)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)


def _gpu_name() -> str:
    out = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
        text=True,
    )
    return out.strip().splitlines()[0]


def _prepare_single_ref_layout() -> None:
    src = ROOT / "data" / "edit3" / "reference" / "sample1" / "1.png"
    dst_dir = ROOT / "data" / "edit3" / "reference_bench_single"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / "sample1.png"
    if not src.is_file():
        raise SystemExit(f"missing {src}")
    if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
        dst.write_bytes(src.read_bytes())


def _parse_log_peaks(log_path: Path) -> dict[str, int | None]:
    if not log_path.is_file():
        return {"first_step_peak_mib": None, "steady_step_peak_mib": None}
    text = log_path.read_text(encoding="utf-8", errors="replace")
    step_markers = list(re.finditer(r"steps:\s+\s*(\d+)%", text))
    first_peak = None
    steady_peak = None
    # fallback: use lines around epoch/step if present
    return {"first_step_peak_mib": first_peak, "steady_step_peak_mib": steady_peak}


def _run_train(label: str, config_rel: str, log_path: Path) -> dict:
    config = ROOT / config_rel
    sampler = GpuSampler()
    sampler.start()
    t0 = time.time()
    proc = subprocess.Popen(
        [
            PYTHON,
            "-m",
            "accelerate.commands.launch",
            "--num_cpu_threads_per_process",
            "1",
            str(ROOT / "scripts" / "dev" / "anima_train_network.py"),
            "--config_file",
            str(config),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    log_lines: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        log_lines.append(line)
        out = f"[{label}] {line}"
        try:
            sys.stdout.write(out)
        except UnicodeEncodeError:
            sys.stdout.buffer.write(out.encode(sys.stdout.encoding or "utf-8", errors="replace"))
        sys.stdout.flush()
    code = proc.wait()
    sampler.stop()
    elapsed = time.time() - t0
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("".join(log_lines), encoding="utf-8")
    if code != 0:
        raise SystemExit(f"{label} failed exit={code}, see {log_path}")
    return {
        "label": label,
        "config": config_rel,
        "exit_code": code,
        "elapsed_s": round(elapsed, 1),
        "nvidia_smi_peak_mib": sampler.peak_mib,
        "log": str(log_path.relative_to(ROOT)).replace("\\", "/"),
    }


def main() -> None:
    _prepare_single_ref_layout()
    out_dir = ROOT / "output" / "anima-edit-vram-bench"
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "date_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gpu": _gpu_name(),
        "resolution": "512,512",
        "dataset": "data/edit3 (1 target sample1)",
        "epochs": 2,
        "notes": "No sample preview; same hyperparams as dual-ref-10epoch.toml",
        "runs": [],
    }
    for label, cfg in (
        ("dual_T3", "docs/examples/anima-edit-vram-bench-dual-2e.toml"),
        ("single_T2", "docs/examples/anima-edit-vram-bench-single-2e.toml"),
    ):
        log = out_dir / f"{label}.log"
        print(f"\n=== {label} ===\n")
        meta["runs"].append(_run_train(label, cfg, log))
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n=== summary ===")
    print(summary_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()

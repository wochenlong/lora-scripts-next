from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import uuid

from mikazuki.download_sources import (
    DownloadSources,
    install_process_env,
    pytorch_extra_index_url,
)
from mikazuki.tasks import LANE_MAINTENANCE, tm
from mikazuki.train_log_hub import hub as train_log_hub

from .extension_state import (
    STATE_AUDITING,
    STATE_BROKEN,
    STATE_INSTALLING,
    STATE_READY,
    ExtensionLayout,
    write_install_state,
)
from .installer import build_install_plan, copy_source_snapshot
from .settings import RuntimeConfig, ensure_install_source_ready, load_backend_config


IMPORT_PROBE = (
    "import torch;"
    "import sys, platform;"
    "import importlib.util;"
    "print(platform.python_version());"
    "print(torch.__version__);"
    "print(torch.cuda.is_available());"
    "print(importlib.util.find_spec('toolkit') is not None);"
    "print(importlib.util.find_spec('diffusers') is not None);"
    "print(importlib.util.find_spec('torchaudio') is not None)"
)

# Upstream requires Python 3.11 (dgx_instructions.md).
TOOLKIT_PYTHON_VERSION = "3.11"
TOOLKIT_PYTORCH_INDEXES = {
    "cu124": "https://download.pytorch.org/whl/cu124",
    "cu128": "https://download.pytorch.org/whl/cu128",
    "cu130": "https://download.pytorch.org/whl/cu130",
    "cu132": "https://download.pytorch.org/whl/cu132",
}
DEFAULT_CUDA_EXTRA = "cu128"
DEFAULT_HF_ENDPOINT = "https://hf-mirror.com"
DEFAULT_PIP_INDEX_URL = "https://pypi.org/simple"
DEFAULT_PYTORCH_INDEX_BASE = "https://download.pytorch.org/whl"


@dataclass
class AuditResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    facts: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "facts": dict(self.facts),
        }


@dataclass(frozen=True)
class EnvironmentInstallPlan:
    project_root: Path
    layout: ExtensionLayout
    source_root: Path
    source_commit: str | None
    python_install_dir: Path
    base_python: Path
    venv_python: Path
    cuda_extra: str
    dry_run: bool = True
    download_sources: DownloadSources | None = None

    def as_dict(self) -> dict:
        return {
            "project_root": str(self.project_root),
            "source_root": str(self.source_root),
            "source_commit": self.source_commit,
            "target_source": str(self.layout.source),
            "python_install_dir": str(self.python_install_dir),
            "base_python": str(self.base_python),
            "venv_python": str(self.venv_python),
            "cuda_extra": self.cuda_extra,
            "dry_run": self.dry_run,
            "download_sources": self.download_sources.as_dict() if self.download_sources else None,
        }


LogFn = Callable[[str], None]
ProgressFn = Callable[[dict], None]

INSTALL_PROGRESS_PHASES = {
    "source": 5,
    "python": 20,
    "venv": 35,
    "dependencies": 70,
    "audit": 90,
    "ready": 100,
    "broken": 90,
}


def resolve_cuda_extra(config: dict | None = None, env: dict[str, str] | None = None) -> str:
    env = env or os.environ
    config = config or load_backend_config()
    extra = (
        str(env.get("AI_TOOLKIT_CUDA_EXTRA", "")).strip()
        or str(config.get("backend", {}).get("cuda_extra", "")).strip()
        or DEFAULT_CUDA_EXTRA
    )
    return extra if extra in TOOLKIT_PYTORCH_INDEXES else DEFAULT_CUDA_EXTRA


def requirements_file(source_root: Path) -> Path:
    """DGX OS (linux aarch64) needs the upstream DGX pin set; everyone else
    takes requirements_base.txt (requirements.txt is just `-r base`)."""
    if sys.platform.startswith("linux") and platform.machine() == "aarch64":
        dgx = source_root / "dgx_requirements.txt"
        if dgx.is_file():
            return dgx
    return source_root / "requirements_base.txt"


# torchcodec==0.9.1 (pinned in upstream requirements_base.txt) ships no
# linux aarch64 wheels — and the Klein image path never imports it (video
# loading goes through lazy `import av`; torchcodec only appears in the
# upstream manager/ and a comment). Strip the pin where no wheel exists.
_PLATFORM_DROPPED_PINS = ("torchcodec",)


def _needs_pin_strip() -> bool:
    return sys.platform.startswith("linux") and platform.machine() in {"aarch64", "arm64"}


def prepare_requirements(source_root: Path, work_dir: Path) -> Path:
    src = requirements_file(source_root)
    if not _needs_pin_strip():
        return src

    def _filter(path: Path) -> Path:
        lines = path.read_text(encoding="utf-8").splitlines()
        kept: list[str] = []
        changed = False
        for line in lines:
            stripped = line.strip()
            if any(stripped.startswith(pkg) for pkg in _PLATFORM_DROPPED_PINS):
                changed = True
                continue
            if stripped.startswith(("-r ", "--requirement ")):
                included = (path.parent / stripped.split(None, 1)[1]).resolve()
                if included.is_file():
                    filtered = _filter(included)
                    if filtered != included:
                        line = f"-r {filtered}"
                        changed = True
            kept.append(line)
        if not changed:
            return path
        work_dir.mkdir(parents=True, exist_ok=True)
        out = work_dir / f".{path.stem}.platform-filtered{path.suffix}"
        out.write_text("\n".join(kept) + "\n", encoding="utf-8")
        return out

    return _filter(src)


def probe_env(runtime: RuntimeConfig) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONNOUSERSITE"] = "1"
    src = str(runtime.toolkit_root.resolve())
    existing = env.get("PYTHONPATH", "")
    parts = [p for p in existing.split(os.pathsep) if p]
    if src not in parts:
        parts.insert(0, src)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def audit_environment(
    runtime: RuntimeConfig,
    check_imports: bool = True,
    layout: ExtensionLayout | None = None,
) -> AuditResult:
    errors: list[str] = []
    warnings: list[str] = []
    facts: dict = {
        "toolkit_root": str(runtime.toolkit_root),
        "python": str(runtime.python),
    }

    if not ((runtime.toolkit_root / "run.py").is_file() and (runtime.toolkit_root / "toolkit").is_dir()):
        errors.append(
            f"ai-toolkit 源码未找到：{runtime.toolkit_root}（缺少 run.py/toolkit）。"
            "请先在「设置 → 训练引擎」安装 ai-toolkit 插件，或拉取 vendor/ai-toolkit"
        )
    if not runtime.python.is_file():
        errors.append(
            f"ai-toolkit 虚拟环境不存在：{runtime.python}。"
            "请在「设置 → 训练引擎」安装 ai-toolkit 插件"
        )

    if not errors and check_imports:
        try:
            result = subprocess.run(
                [str(runtime.python), "-c", IMPORT_PROBE],
                env=probe_env(runtime),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=180,
                encoding="utf-8",
                errors="replace",
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"ai-toolkit 环境探测失败：{exc}")
            result = None

        if result is not None:
            lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
            if result.returncode != 0 or len(lines) < 6:
                tail = " | ".join(lines[-3:]) if lines else "<no output>"
                errors.append(f"ai-toolkit 依赖自检失败（import torch/toolkit）：{tail}")
            else:
                facts["python_version"] = lines[-6]
                facts["torch_version"] = lines[-5]
                facts["cuda_available"] = lines[-4]
                facts["toolkit_available"] = lines[-3]
                facts["diffusers_available"] = lines[-2]
                facts["torchaudio_available"] = lines[-1]
                if not lines[-6].startswith("3.11"):
                    errors.append(f"ai-toolkit 要求 Python 3.11，当前为 {lines[-6]}")
                if lines[-4] != "True":
                    errors.append("ai-toolkit 环境的 torch 未检测到 CUDA，无法训练")
                if lines[-3] != "True":
                    errors.append("ai-toolkit 环境缺少 toolkit 包（源码树不可导入）")
                if lines[-2] != "True":
                    errors.append("ai-toolkit 环境缺少 diffusers")
                if lines[-1] != "True":
                    errors.append("ai-toolkit 环境缺少 torchaudio（config_modules 顶层 import，上游未声明）")

    result_obj = AuditResult(ok=not errors, errors=errors, warnings=warnings, facts=facts)
    if layout is not None:
        layout.root.mkdir(parents=True, exist_ok=True)
        layout.audit_result.write_text(json.dumps(result_obj.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return result_obj


def build_environment_install_plan(
    project_root: Path,
    layout: ExtensionLayout,
    source_root: Path,
    dry_run: bool = True,
    source_commit: str | None = None,
    cuda_extra: str | None = None,
    download_sources: DownloadSources | None = None,
) -> EnvironmentInstallPlan:
    root = project_root.resolve()
    python_dir = root / ".python"
    if sys.platform == "win32":
        base_python = python_dir / f"cpython-{TOOLKIT_PYTHON_VERSION}-windows-x86_64-none" / "python.exe"
        venv_python = layout.root / ".venv" / "Scripts" / "python.exe"
    else:
        base_python = python_dir / f"cpython-{TOOLKIT_PYTHON_VERSION}-linux-aarch64-gnu" / "bin" / "python3"
        if platform.machine() not in {"aarch64", "arm64"}:
            base_python = python_dir / f"cpython-{TOOLKIT_PYTHON_VERSION}-linux-x86_64-gnu" / "bin" / "python3"
        venv_python = layout.root / ".venv" / "bin" / "python"
    return EnvironmentInstallPlan(
        project_root=root,
        layout=layout,
        source_root=source_root.resolve(),
        source_commit=source_commit,
        python_install_dir=python_dir,
        base_python=base_python,
        venv_python=venv_python,
        cuda_extra=cuda_extra or resolve_cuda_extra(),
        dry_run=dry_run,
        download_sources=download_sources,
    )


def _append(log: LogFn, line: str) -> None:
    log(line)


def _emit_progress(progress: ProgressFn | None, phase: str, message: str, percent: int | None = None, **extra) -> None:
    if not progress:
        return
    event = {
        "type": "progress",
        "phase": phase,
        "percent": int(percent if percent is not None else INSTALL_PROGRESS_PHASES.get(phase, 0)),
        "message": message,
    }
    event.update({key: value for key, value in extra.items() if value is not None})
    try:
        progress(event)
    except Exception:
        pass


def _run_streaming_once(command: list[str], cwd: Path, log: LogFn, env: dict[str, str] | None = None) -> None:
    _append(log, "[cmd] " + " ".join(command))
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    if (
        sys.platform == "win32"
        and "UV_SYSTEM_CERTS" not in merged_env
        and "UV_NATIVE_TLS" not in merged_env
    ):
        merged_env["UV_SYSTEM_CERTS"] = "true"
    merged_env.update({
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
        "PYTHONNOUSERSITE": "1",
        "UV_HTTP_TIMEOUT": merged_env.get("UV_HTTP_TIMEOUT", "300"),
        "UV_CONCURRENT_DOWNLOADS": merged_env.get("UV_CONCURRENT_DOWNLOADS", "2"),
        "HF_ENDPOINT": merged_env.get("HF_ENDPOINT", DEFAULT_HF_ENDPOINT),
    })
    completed = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=merged_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert completed.stdout is not None
    for line in iter(completed.stdout.readline, ""):
        _append(log, line.rstrip("\r\n"))
    returncode = completed.wait()
    _append(log, f"[exit] returncode={returncode}")
    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, command)


def _run_streaming(command: list[str], cwd: Path, log: LogFn, env: dict[str, str] | None = None, retries: int = 0) -> None:
    attempt = 0
    while True:
        try:
            _run_streaming_once(command, cwd, log, env)
            return
        except subprocess.CalledProcessError:
            attempt += 1
            if attempt > retries:
                raise
            delay = min(30, 5 * attempt)
            _append(log, f"[retry] command failed; retry {attempt}/{retries} after {delay}s")
            time.sleep(delay)


def _uv_command() -> str:
    resolved = shutil.which("uv")
    if not resolved:
        raise FileNotFoundError("uv executable was not found in PATH")
    return resolved


def _find_base_python(plan: EnvironmentInstallPlan) -> Path:
    if plan.base_python.is_file():
        return plan.base_python
    patterns = [f"cpython-{TOOLKIT_PYTHON_VERSION}.*-windows-*/python.exe"]
    if sys.platform != "win32":
        patterns = [
            f"cpython-{TOOLKIT_PYTHON_VERSION}.*-linux*/bin/python3",
            f"cpython-{TOOLKIT_PYTHON_VERSION}.*-linux*/bin/python",
        ]
    for pattern in patterns:
        candidates = sorted(plan.python_install_dir.glob(pattern), reverse=True)
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
    return plan.base_python


def _runtime_for_layout(plan: EnvironmentInstallPlan) -> RuntimeConfig:
    root = plan.layout.source.resolve()
    lora_next_root = plan.project_root
    return RuntimeConfig(
        toolkit_root=root,
        python=plan.venv_python,
        lora_next_root=lora_next_root,
        output_dir=(lora_next_root / "output" / "ai-toolkit").resolve(),
        logging_dir=(lora_next_root / "logs" / "ai-toolkit").resolve(),
        cache_dir=(lora_next_root / ".cache" / "ai-toolkit").resolve(),
    )


def install_environment(
    plan: EnvironmentInstallPlan,
    log: LogFn = print,
    task_id: str | None = None,
    progress: ProgressFn | None = None,
) -> AuditResult:
    facts: dict = {"plan": plan.as_dict(), "phase": "source"}
    if task_id:
        facts["task_id"] = task_id
    _emit_progress(progress, "source", "Preparing ai-toolkit runtime source")
    write_install_state(plan.layout, STATE_INSTALLING, facts, "copying ai-toolkit source snapshot")
    _append(log, "[phase] copy source snapshot")
    if plan.source_commit:
        _append(log, f"[source] pinned commit {plan.source_commit}")
    github_prefix = plan.download_sources.github_url_prefix if plan.download_sources else None
    resolved_source = ensure_install_source_ready(
        plan.project_root,
        plan.source_root,
        plan.source_commit,
        log=lambda line: _append(log, line),
        github_url_prefix=github_prefix,
    )
    copy_source_snapshot(
        build_install_plan(resolved_source, plan.layout, dry_run=False, source_commit=plan.source_commit, cuda_extra=plan.cuda_extra)
    )

    process_env = install_process_env(plan.download_sources)
    pip_index = (
        plan.download_sources.pip_index_url
        if plan.download_sources and plan.download_sources.pip_index_url
        else DEFAULT_PIP_INDEX_URL
    )
    default_torch = TOOLKIT_PYTORCH_INDEXES.get(plan.cuda_extra) or f"{DEFAULT_PYTORCH_INDEX_BASE}/{plan.cuda_extra}"
    torch_index = pytorch_extra_index_url(
        plan.download_sources.pytorch_index_url if plan.download_sources else None,
        plan.cuda_extra,
        default_torch,
    )
    if plan.download_sources:
        _append(
            log,
            f"[sources] pip={pip_index} pytorch={torch_index} "
            f"hf={plan.download_sources.hf_endpoint or '(default)'} github_prefix={github_prefix or '(none)'}",
        )

    uv = _uv_command()
    facts["phase"] = "python"
    _emit_progress(progress, "python", f"Installing or locating Python {TOOLKIT_PYTHON_VERSION} runtime")
    write_install_state(plan.layout, STATE_INSTALLING, facts, "preparing Python runtime")
    base_python = _find_base_python(plan)
    if not base_python.is_file():
        plan.python_install_dir.mkdir(parents=True, exist_ok=True)
        _run_streaming(
            [uv, "python", "install", TOOLKIT_PYTHON_VERSION, "--install-dir", str(plan.python_install_dir)],
            plan.project_root,
            log,
            env=process_env,
        )
        base_python = _find_base_python(plan)
    if not base_python.is_file():
        raise FileNotFoundError(f"Python {TOOLKIT_PYTHON_VERSION} runtime was not installed under {plan.python_install_dir}")
    facts["base_python"] = str(base_python)
    _append(log, f"[info] Python runtime: {base_python}")

    facts["phase"] = "venv"
    _emit_progress(progress, "venv", "Creating ai-toolkit extension virtual environment")
    write_install_state(plan.layout, STATE_INSTALLING, facts, "creating ai-toolkit extension venv")
    if not plan.venv_python.is_file():
        plan.venv_python.parent.parent.mkdir(parents=True, exist_ok=True)
        _run_streaming(
            [str(base_python), "-m", "venv", str(plan.venv_python.parent.parent)],
            plan.project_root,
            log,
            env=process_env,
        )
    else:
        _append(log, f"[skip] ai-toolkit venv exists: {plan.venv_python}")

    facts["phase"] = "dependencies"
    _emit_progress(progress, "dependencies", "Installing ai-toolkit Python dependencies")
    write_install_state(plan.layout, STATE_INSTALLING, facts, "installing ai-toolkit dependencies")
    # torch is intentionally absent from upstream requirements; install the
    # torch stack first from the CUDA-specific index, then the pinned
    # requirement set. torchaudio is likewise undeclared upstream but
    # top-level-imported by toolkit/config_modules.py.
    _run_streaming(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(plan.venv_python),
            "--no-config",
            "--index-url",
            torch_index,
            "torch",
            "torchvision",
            "torchaudio",
        ],
        plan.project_root,
        log,
        env=process_env,
        retries=int(os.environ.get("AI_TOOLKIT_INSTALL_RETRIES", "3")),
    )
    requirements = prepare_requirements(plan.layout.source, plan.layout.root)
    if requirements.name.startswith("."):
        _append(log, f"[deps] stripped platform-unsupported pins ({', '.join(_PLATFORM_DROPPED_PINS)}) -> {requirements.name}")
    _run_streaming(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(plan.venv_python),
            "--no-config",
            "--index-url",
            pip_index,
            "--extra-index-url",
            torch_index,
            "--index-strategy",
            "unsafe-best-match",
            "-r",
            str(requirements),
        ],
        plan.project_root,
        log,
        env=process_env,
        retries=int(os.environ.get("AI_TOOLKIT_INSTALL_RETRIES", "3")),
    )

    facts["phase"] = "audit"
    _emit_progress(progress, "audit", "Auditing ai-toolkit environment")
    write_install_state(plan.layout, STATE_AUDITING, facts, "auditing ai-toolkit environment")
    result = audit_environment(_runtime_for_layout(plan), layout=plan.layout)
    final_facts = dict(facts)
    final_facts["phase"] = "ready" if result.ok else "audit_failed"
    final_facts["audit"] = result.as_dict()
    if result.ok:
        write_install_state(plan.layout, STATE_READY, final_facts, "audit passed")
        _emit_progress(progress, "ready", "ai-toolkit environment is ready", percent=100, state="ready")
        _append(log, "[ready] ai-toolkit environment verified")
    else:
        write_install_state(plan.layout, STATE_BROKEN, final_facts, "; ".join(result.errors))
        _emit_progress(progress, "broken", "ai-toolkit environment audit failed", state="broken")
        _append(log, "[broken] ai-toolkit environment audit failed")
    return result


def start_install_task(
    project_root: Path,
    layout: ExtensionLayout,
    source_root: Path,
    dry_run: bool = False,
    source_commit: str | None = None,
    cuda_extra: str | None = None,
    download_sources: DownloadSources | None = None,
) -> tuple[str, dict]:
    plan = build_environment_install_plan(
        project_root,
        layout,
        source_root,
        dry_run=dry_run,
        source_commit=source_commit,
        cuda_extra=cuda_extra,
        download_sources=download_sources,
    )
    if dry_run:
        return "", {"plan": plan.as_dict()}

    task_id = f"ai-toolkit-install-{uuid.uuid4()}"
    task = tm.create_task(
        ["ai-toolkit-install"],
        os.environ.copy(),
        metadata={"kind": "ai_toolkit_install", "plan": plan.as_dict()},
        cwd=str(project_root),
        task_id=task_id,
        lane=LANE_MAINTENANCE,
    )
    task.start_log_only()
    write_install_state(plan.layout, STATE_INSTALLING, {"plan": plan.as_dict(), "task_id": task_id}, "install task queued")

    def runner() -> None:
        def log(line: str) -> None:
            train_log_hub.append_line(task_id, line)

        def progress(event: dict) -> None:
            train_log_hub.append_event(task_id, event)

        try:
            log("[start] ai-toolkit plugin installation")
            result = install_environment(plan, log, task_id=task_id, progress=progress)
            task.metadata["audit"] = result.as_dict()
            task.finish_log_only(0 if result.ok else 1, None if result.ok else "; ".join(result.errors))
        except (Exception, KeyboardInterrupt) as exc:  # install failures must become observable state
            facts = {"plan": plan.as_dict(), "phase": "failed", "task_id": task_id}
            write_install_state(plan.layout, STATE_BROKEN, facts, str(exc))
            log(f"[error] {exc}")
            task.finish_log_only(1, exc)

    threading.Thread(target=runner, daemon=True).start()
    return task_id, {
        "task_id": task_id,
        "plan": plan.as_dict(),
        "log_stream": f"/api/engines/ai-toolkit/install/log/stream/{task_id}",
        "progress_stream": f"/api/engines/ai-toolkit/install/progress/stream/{task_id}",
    }

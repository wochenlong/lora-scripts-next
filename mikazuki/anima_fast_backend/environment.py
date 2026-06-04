from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import time
import threading
import uuid

from mikazuki.tasks import Task, tm
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


ENVIRONMENT_DIR = Path("config/anima_fast_environment")
ANIMA_CONSTRAINTS = ENVIRONMENT_DIR / "anima-constraints-cu130.txt"
ANIMA_OVERRIDES = ENVIRONMENT_DIR / "anima-overrides-cu130.txt"
MAIN_CONSTRAINTS = ENVIRONMENT_DIR / "main-constraints-cu130.txt"
FLASH_ATTN_WINDOWS_MARKER = "flash-attn @ https://"
FLASH_ATTN_LINUX_PLATFORM_MARKER = "sys_platform == 'linux'"
FLASH_ATTN_LINUX_CU130_URL = (
    "https://github.com/mjun0812/flash-attention-prebuild-wheels/releases/download/v0.9.4/"
    "flash_attn-2.8.3%2Bcu130torch2.11-cp313-cp313-linux_x86_64.whl"
)

ANIMA_OPTIMIZER_PACKAGES = {
    "bitsandbytes": "0.49.2",
    "dadaptation": "3.1",
    "lion-pytorch": "0.2.3",
    "prodigyopt": "1.1.2",
    "schedulefree": "1.4",
    "pytorch-optimizer": "3.9.0",
}

ANIMA_OPTIMIZER_IMPORTS = [
    "bitsandbytes",
    "dadaptation",
    "lion_pytorch",
    "prodigyopt",
    "schedulefree",
    "optimum.quanto",
]

# Constraints pin versions but do not install these; uv must receive explicit targets.
ANIMA_EXTRA_PIP_TARGETS = ("optimum-quanto>=0.2.0",)


def anima_pip_dependency_targets() -> list[str]:
    targets = [f"{name}=={version}" for name, version in ANIMA_OPTIMIZER_PACKAGES.items()]
    targets.extend(ANIMA_EXTRA_PIP_TARGETS)
    return targets

ANIMA_EXPECTED = {
    "python_major_minor": "3.13",
    "exact": {
        "torch": "2.11.0+cu130",
        "torchvision": "0.26.0+cu130",
        "flash-attn": "2.8.3+cu130torch2.11",
        "triton-windows": "3.7.0.post26",
        "transformers": "5.9.0",
        "diffusers": "0.37.1",
        "accelerate": "1.13.0",
        "safetensors": "0.7.0",
        "iopath": "0.1.10",
        "bitsandbytes": ANIMA_OPTIMIZER_PACKAGES["bitsandbytes"],
        "dadaptation": ANIMA_OPTIMIZER_PACKAGES["dadaptation"],
    },
}

ANIMA_LINUX_EXACT_OVERRIDES = {
    "torch": "2.12.0+cu130",
    "torchvision": "0.27.0+cu130",
}

ANIMA_WINDOWS_ONLY_EXACT = {"triton-windows"}

MAIN_EXPECTED = {
    "python_major_minor": None,
    "exact": {
        "numpy": "1.26.4",
        "opencv-python": "4.8.1.78",
    },
    "alternatives": {
        "opencv-python": ["opencv-python-headless"],
    },
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
    constraints: Path
    overrides: Path
    dry_run: bool = True

    def as_dict(self) -> dict:
        return {
            "project_root": str(self.project_root),
            "source_root": str(self.source_root),
            "source_commit": self.source_commit,
            "target_source": str(self.layout.source),
            "python_install_dir": str(self.python_install_dir),
            "base_python": str(self.base_python),
            "venv_python": str(self.venv_python),
            "constraints": str(self.constraints),
            "overrides": str(self.overrides),
            "dry_run": self.dry_run,
        }


@dataclass
class AuditResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    facts: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "facts": self.facts,
        }


LogFn = Callable[[str], None]


def _resolve_child(root: Path, child: Path) -> Path:
    resolved = child.resolve()
    resolved.relative_to(root.resolve())
    return resolved


def build_environment_install_plan(
    project_root: Path,
    layout: ExtensionLayout,
    source_root: Path,
    dry_run: bool = True,
    source_commit: str | None = None,
) -> EnvironmentInstallPlan:
    root = project_root.resolve()
    extension_root = _resolve_child(root, layout.root)
    python_dir = _resolve_child(root, root / ".python")
    if sys.platform == "win32":
        base_python = python_dir / "cpython-3.13.13-windows-x86_64-none" / "python.exe"
        venv_python = extension_root / ".venv" / "Scripts" / "python.exe"
    else:
        base_python = python_dir / "cpython-3.13.13-linux-x86_64-gnu" / "bin" / "python3"
        venv_python = extension_root / ".venv" / "bin" / "python"
    env_dir = root / ENVIRONMENT_DIR
    constraints = env_dir / ANIMA_CONSTRAINTS.name
    overrides = env_dir / ANIMA_OVERRIDES.name
    return EnvironmentInstallPlan(
        project_root=root,
        layout=ExtensionLayout(extension_root),
        source_root=source_root.resolve(),
        source_commit=source_commit,
        python_install_dir=python_dir,
        base_python=base_python,
        venv_python=venv_python,
        constraints=constraints,
        overrides=overrides,
        dry_run=dry_run,
    )


def _append(log: LogFn, line: str) -> None:
    log(line)


def _replace_flash_attn_dependency(source_root: Path, platform_marker: str, replacement: str, log: LogFn) -> list[str]:
    pyproject = source_root / "pyproject.toml"
    if not pyproject.is_file():
        return []
    lines = pyproject.read_text(encoding="utf-8").splitlines(keepends=True)
    changed: list[str] = []
    patched: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if (
            not stripped.startswith("#")
            and FLASH_ATTN_WINDOWS_MARKER in line
            and platform_marker in line
        ):
            indent = line[: len(line) - len(stripped)]
            patched.append(indent + replacement + ("\n" if line.endswith("\n") else ""))
            changed.append(line.strip())
            continue
        patched.append(line)
    if changed:
        pyproject.write_text("".join(patched), encoding="utf-8")
        for dependency in changed:
            _append(log, f"[patch] localized Linux cu130 flash-attn dependency: {dependency}")
    return changed


def localize_linux_flash_attn_dependency(source_root: Path, log: LogFn = print) -> list[str]:
    if not sys.platform.startswith("linux"):
        return []
    replacement = f'"flash-attn @ {FLASH_ATTN_LINUX_CU130_URL} ; {FLASH_ATTN_LINUX_PLATFORM_MARKER}",'
    return _replace_flash_attn_dependency(source_root, FLASH_ATTN_LINUX_PLATFORM_MARKER, replacement, log)


def _anima_expected_for_platform(platform: str | None = None) -> dict:
    platform = platform or sys.platform
    expected = {
        "python_major_minor": ANIMA_EXPECTED["python_major_minor"],
        "exact": dict(ANIMA_EXPECTED["exact"]),
    }
    if platform.startswith("linux"):
        for package in ANIMA_WINDOWS_ONLY_EXACT:
            expected["exact"].pop(package, None)
        expected["exact"].update(ANIMA_LINUX_EXACT_OVERRIDES)
    return expected


def _run_streaming_once(command: list[str], cwd: Path, log: LogFn, env: dict[str, str] | None = None) -> None:
    _append(log, "[cmd] " + " ".join(command))
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    merged_env.update({
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
        "PYTHONNOUSERSITE": "1",
        "UV_HTTP_TIMEOUT": merged_env.get("UV_HTTP_TIMEOUT", "300"),
        "UV_CONCURRENT_DOWNLOADS": merged_env.get("UV_CONCURRENT_DOWNLOADS", "2"),
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
    patterns = ["cpython-3.13.*-windows-*/python.exe"]
    if sys.platform != "win32":
        patterns = ["cpython-3.13.*-linux*/bin/python3", "cpython-3.13.*-linux*/bin/python"]
    for pattern in patterns:
        candidates = sorted(plan.python_install_dir.glob(pattern), reverse=True)
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
    return plan.base_python


def install_environment(plan: EnvironmentInstallPlan, log: LogFn = print) -> AuditResult:
    facts = {"plan": plan.as_dict(), "phase": "source"}
    write_install_state(plan.layout, STATE_INSTALLING, facts, "copying Anima source snapshot")
    _append(log, "[phase] copy source snapshot")
    if plan.source_commit:
        _append(log, f"[source] pinned commit {plan.source_commit}")
    copy_source_snapshot(build_install_plan(plan.source_root, plan.layout, dry_run=False, source_commit=plan.source_commit))
    localized_direct_urls = localize_linux_flash_attn_dependency(plan.layout.source, log)
    if localized_direct_urls:
        facts["localized_direct_url_dependencies"] = localized_direct_urls

    if not plan.constraints.is_file():
        raise FileNotFoundError(f"Anima constraints file missing: {plan.constraints}")
    if not plan.overrides.is_file():
        raise FileNotFoundError(f"Anima overrides file missing: {plan.overrides}")

    uv = _uv_command()
    facts["phase"] = "python"
    write_install_state(plan.layout, STATE_INSTALLING, facts, "preparing Python 3.13 runtime")
    base_python = _find_base_python(plan)
    if not base_python.is_file():
        plan.python_install_dir.mkdir(parents=True, exist_ok=True)
        _run_streaming(
            [uv, "python", "install", "3.13", "--install-dir", str(plan.python_install_dir), "--reinstall", "--no-cache"],
            plan.project_root,
            log,
        )
        base_python = _find_base_python(plan)
    if not base_python.is_file():
        raise FileNotFoundError(f"Python 3.13 runtime was not installed under {plan.python_install_dir}")
    facts["base_python"] = str(base_python)
    if base_python != plan.base_python:
        _append(log, f"[info] Python runtime discovered: {base_python}")
    else:
        _append(log, f"[skip] Python runtime exists: {base_python}")

    facts["phase"] = "venv"
    write_install_state(plan.layout, STATE_INSTALLING, facts, "creating Anima extension venv")
    if not plan.venv_python.is_file():
        plan.venv_python.parent.parent.mkdir(parents=True, exist_ok=True)
        _run_streaming([str(base_python), "-m", "venv", str(plan.venv_python.parent.parent)], plan.project_root, log)
    else:
        _append(log, f"[skip] Anima venv exists: {plan.venv_python}")

    facts["phase"] = "dependencies"
    write_install_state(plan.layout, STATE_INSTALLING, facts, "installing Anima dependencies")
    pip_targets = [*anima_pip_dependency_targets(), str(plan.layout.source)]
    _run_streaming(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(plan.venv_python),
            "--no-cache",
            "--no-config",
            "--index-url",
            "https://pypi.org/simple",
            "--extra-index-url",
            "https://download.pytorch.org/whl/cu130",
            "--index-strategy",
            "unsafe-best-match",
            "--constraints",
            str(plan.constraints),
            "--overrides",
            str(plan.overrides),
            *pip_targets,
        ],
        plan.project_root,
        log,
        retries=int(os.environ.get("ANIMA_FAST_INSTALL_RETRIES", "3")),
    )

    facts["phase"] = "audit"
    write_install_state(plan.layout, STATE_AUDITING, facts, "auditing Anima environment")
    result = audit_environment(plan.project_root, plan.layout, main_python=Path(sys.executable), require_cuda=True)
    plan.layout.audit_result.write_text(json.dumps(result.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    final_facts = dict(facts)
    final_facts["phase"] = "ready" if result.ok else "audit_failed"
    final_facts["audit"] = result.as_dict()
    if result.ok:
        write_install_state(plan.layout, STATE_READY, final_facts, "audit passed")
        _append(log, "[ready] Anima Fast environment audit passed")
    else:
        write_install_state(plan.layout, STATE_BROKEN, final_facts, "; ".join(result.errors))
        _append(log, "[broken] Anima Fast environment audit failed")
    return result


def _collect_python_facts(python: Path, packages: list[str], imports: list[str], cwd: Path) -> dict:
    script = f"""
import importlib, importlib.metadata, json, platform, sys
facts = {{
    "python": sys.executable,
    "version": platform.python_version(),
    "prefix": sys.prefix,
    "base_prefix": sys.base_prefix,
    "packages": {{}},
    "imports": {{}},
}}
for name in {packages!r}:
    try:
        facts["packages"][name] = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        facts["packages"][name] = None
for name in {imports!r}:
    try:
        importlib.import_module(name)
        facts["imports"][name] = True
    except Exception as exc:
        facts["imports"][name] = repr(exc)
try:
    import torch
    facts["torch_cuda_available"] = bool(torch.cuda.is_available())
    facts["torch_cuda"] = getattr(torch.version, "cuda", "")
    if torch.cuda.is_available():
        facts["gpu"] = torch.cuda.get_device_name(0)
except Exception as exc:
    facts["torch_error"] = repr(exc)
print(json.dumps(facts, ensure_ascii=False))
"""
    completed = subprocess.run(
        [str(python), "-c", script],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONNOUSERSITE": "1"},
    )
    if completed.returncode != 0:
        return {
            "subprocess_error": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "python": str(python),
        }
    try:
        return json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        return {"subprocess_error": "json_decode", "error": str(exc), "stdout": completed.stdout, "python": str(python)}


def _path_within(path_text: str, root: Path) -> bool:
    try:
        Path(path_text).resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _check_facts(
    label: str,
    facts: dict,
    expected: dict,
    root: Path,
    errors: list[str],
    require_cuda: bool,
    require_inside_root: bool,
) -> None:
    if "subprocess_error" in facts:
        errors.append(f"{label}: audit subprocess failed: {facts.get('stderr') or facts.get('error')}")
        return
    for key in ("python", "prefix", "base_prefix"):
        value = facts.get(key)
        if require_inside_root and value and not _path_within(value, root):
            errors.append(f"{label}: {key} is outside project root: {value}")
    major_minor = expected.get("python_major_minor")
    if major_minor and not str(facts.get("version", "")).startswith(major_minor + "."):
        errors.append(f"{label}: expected Python {major_minor}.x, got {facts.get('version') or 'unknown'}")
    for package, version in expected["exact"].items():
        actual = facts.get("packages", {}).get(package)
        if actual == version:
            continue
        alternatives = expected.get("alternatives", {}).get(package, [])
        matched_alternative = next(
            (
                alternative
                for alternative in alternatives
                if facts.get("packages", {}).get(alternative) == version
            ),
            None,
        )
        if matched_alternative:
            continue
        if alternatives:
            detail = ", ".join(
                f"{name}={facts.get('packages', {}).get(name)}"
                for name in [package, *alternatives]
            )
            errors.append(f"{label}: {package} expected {version} or equivalent, got {detail}")
        else:
            errors.append(f"{label}: {package} expected {version}, got {actual}")
    if require_cuda and not facts.get("torch_cuda_available"):
        errors.append(f"{label}: torch.cuda is not available")
    for module, value in facts.get("imports", {}).items():
        if value is not True:
            errors.append(f"{label}: import {module} failed: {value}")


def _main_facts_in_process() -> dict:
    package_names = set(MAIN_EXPECTED["exact"])
    for alternatives in MAIN_EXPECTED.get("alternatives", {}).values():
        package_names.update(alternatives)
    packages = {name: None for name in sorted(package_names)}
    for name in packages:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    imports = {}
    for name in ("cv2", "torch"):
        try:
            __import__(name)
            imports[name] = True
        except Exception as exc:
            imports[name] = repr(exc)
    facts = {
        "python": sys.executable,
        "version": sys.version.split()[0],
        "prefix": sys.prefix,
        "base_prefix": sys.base_prefix,
        "packages": packages,
        "imports": imports,
    }
    try:
        import torch

        facts["torch_cuda_available"] = bool(torch.cuda.is_available())
        facts["torch_cuda"] = getattr(torch.version, "cuda", "")
    except Exception as exc:
        facts["torch_error"] = repr(exc)
    return facts


def audit_environment(
    project_root: Path,
    layout: ExtensionLayout,
    main_python: Path | None = None,
    require_cuda: bool = True,
    require_main_inside_root: bool = False,
) -> AuditResult:
    root = project_root.resolve()
    errors: list[str] = []
    warnings: list[str] = []
    if not layout.train_py.is_file():
        errors.append(f"anima: extension source train.py missing: {layout.train_py}")
    if not layout.venv_python.is_file():
        errors.append(f"anima: extension venv python missing: {layout.venv_python}")

    main_python = main_python or Path(sys.executable)
    main_facts = _main_facts_in_process() if main_python.resolve() == Path(sys.executable).resolve() else _collect_python_facts(
        main_python,
        sorted(set(MAIN_EXPECTED["exact"]) | {name for names in MAIN_EXPECTED.get("alternatives", {}).values() for name in names}),
        ["cv2", "torch"],
        root,
    )
    anima_expected = _anima_expected_for_platform()
    anima_facts = (
        _collect_python_facts(
            layout.venv_python,
            sorted(set(anima_expected["exact"]) | {"numpy", "opencv-python"}),
            ["torch", "flash_attn", "triton", "transformers", "diffusers", *ANIMA_OPTIMIZER_IMPORTS],
            layout.source if layout.source.is_dir() else root,
        )
        if layout.venv_python.is_file()
        else {"subprocess_error": "missing", "python": str(layout.venv_python)}
    )
    _check_facts("main", main_facts, MAIN_EXPECTED, root, errors, require_cuda=False, require_inside_root=require_main_inside_root)
    _check_facts("anima", anima_facts, anima_expected, root, errors, require_cuda=require_cuda, require_inside_root=True)
    result = AuditResult(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        facts={
            "project_root": str(root),
            "source": str(layout.source),
            "python": str(layout.venv_python),
            "main": main_facts,
            "anima": anima_facts,
        },
    )
    layout.root.mkdir(parents=True, exist_ok=True)
    layout.audit_result.write_text(json.dumps(result.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def start_install_task(
    project_root: Path,
    layout: ExtensionLayout,
    source_root: Path,
    dry_run: bool = False,
    source_commit: str | None = None,
) -> tuple[str, dict]:
    plan = build_environment_install_plan(project_root, layout, source_root, dry_run=dry_run, source_commit=source_commit)
    if dry_run:
        return "", {"plan": plan.as_dict()}

    task_id = f"anima-install-{uuid.uuid4()}"
    task = Task(
        task_id=task_id,
        command=["anima-fast-install"],
        environ=os.environ.copy(),
        metadata={"kind": "anima_fast_install", "plan": plan.as_dict()},
        cwd=str(project_root),
    )
    tm.add_task(task_id, task)
    task.start_log_only()
    write_install_state(plan.layout, STATE_INSTALLING, {"plan": plan.as_dict(), "task_id": task_id}, "install task queued")

    def runner() -> None:
        nonlocal plan

        def log(line: str) -> None:
            train_log_hub.append_line(task_id, line)

        try:
            log("[start] Anima Fast plugin installation")
            from .source_root import ensure_install_source_ready

            resolved_source = ensure_install_source_ready(
                plan.project_root, plan.source_root, plan.source_commit, log=log
            )
            if resolved_source != plan.source_root:
                plan = replace(plan, source_root=resolved_source)
            result = install_environment(plan, log)
            task.metadata["audit"] = result.as_dict()
            task.finish_log_only(0 if result.ok else 1, None if result.ok else "; ".join(result.errors))
        except (Exception, KeyboardInterrupt) as exc:  # install failures must become observable state
            facts = {"plan": plan.as_dict(), "phase": "failed", "task_id": task_id}
            write_install_state(plan.layout, STATE_BROKEN, facts, str(exc))
            log(f"[error] {exc}")
            task.finish_log_only(1, exc)

    threading.Thread(target=runner, daemon=True).start()
    return task_id, {"task_id": task_id, "plan": plan.as_dict(), "log_stream": f"/api/plugins/anima-lora/install/log/stream/{task_id}"}

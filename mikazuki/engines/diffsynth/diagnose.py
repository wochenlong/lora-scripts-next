"""Structural + light executable diagnosis for DiffSynth (#462)."""
from __future__ import annotations

import subprocess
from typing import Any, Callable

from .environment import process_env
from .manifest import UPSTREAM
from .settings import TRAIN_SCRIPT

RunCmd = Callable[..., subprocess.CompletedProcess]


def _run(cmd, *, cwd=None, env=None, timeout=120) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=timeout,
    )


def _extension_empty(runtime) -> bool:
    if not runtime.root.exists():
        return True
    try:
        next(runtime.root.iterdir())
    except StopIteration:
        return True
    return False


def _git_head(runtime, run: RunCmd) -> str:
    if not (runtime.source / ".git").exists() and not runtime.source.exists():
        return ""
    result = run(["git", "-C", str(runtime.source), "rev-parse", "HEAD"], cwd=None, env=None)
    return (result.stdout or "").strip() if result.returncode == 0 else ""


def _result(
    code: str,
    *,
    severity: str,
    summary: str,
    detail: str = "",
    components: dict[str, str],
    recommended_actions: list[str],
    allows_full_reinstall: bool,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "summary": summary,
        "detail": detail,
        "components": components,
        "recommended_actions": recommended_actions,
        "allows_full_reinstall": allows_full_reinstall,
    }


def diagnose(runtime, *, run: RunCmd | None = None) -> dict[str, Any]:
    """Return a diagnosis dict. Does not mutate the filesystem."""
    run = run or _run
    unknown = {
        "python_runtime": "unknown",
        "venv": "unknown",
        "source": "unknown",
        "state": "present" if runtime.state_file.exists() else "missing",
    }

    if _extension_empty(runtime):
        return _result(
            "missing_all",
            severity="info",
            summary="尚未安装 DiffSynth 运行时",
            components={
                "python_runtime": "missing",
                "venv": "missing",
                "source": "missing",
                "state": unknown["state"],
            },
            recommended_actions=["fresh_install"],
            allows_full_reinstall=False,
        )

    python_dir_ok = runtime.python_install_dir.exists()
    venv_python_ok = runtime.python.is_file()
    source_exists = runtime.source.exists()
    train_ok = (runtime.source / TRAIN_SCRIPT).is_file()
    pyproject_ok = (runtime.source / "pyproject.toml").is_file()

    components = {
        "python_runtime": "ok" if python_dir_ok else "missing",
        "venv": "ok" if venv_python_ok else "missing",
        "source": "ok" if (source_exists and train_ok and pyproject_ok) else ("missing" if not source_exists else "broken"),
        "state": unknown["state"],
    }

    if not python_dir_ok:
        return _result(
            "python_runtime_missing",
            severity="error",
            summary="独立 Python（.python）缺失或不可用",
            components=components,
            recommended_actions=["repair_python_runtime", "refresh_state"],
            allows_full_reinstall=True,
        )

    if not venv_python_ok:
        return _result(
            "venv_missing",
            severity="error",
            summary="虚拟环境解释器缺失",
            components=components,
            recommended_actions=["repair_venv", "refresh_state"],
            allows_full_reinstall=True,
        )

    if not source_exists or not train_ok or not pyproject_ok:
        return _result(
            "source_incomplete",
            severity="error",
            summary="源码或训练入口不完整",
            detail="" if train_ok else f"缺少 {TRAIN_SCRIPT}",
            components=components,
            recommended_actions=["repair_source", "refresh_state"],
            allows_full_reinstall=True,
        )

    head = _git_head(runtime, run)
    if head and head != UPSTREAM["commit"]:
        components["source"] = "broken"
        return _result(
            "source_wrong_revision",
            severity="error",
            summary="源码 commit 与产品钉扎版本不一致",
            detail=f"have={head} want={UPSTREAM['commit']}",
            components=components,
            recommended_actions=["repair_source", "refresh_state"],
            allows_full_reinstall=True,
        )

    # Light executable probes (no model weights).
    probe = run([str(runtime.python), "-c", "import sys; print(sys.executable)"], cwd=str(runtime.source), env=process_env())
    if probe.returncode:
        components["venv"] = "broken"
        return _result(
            "venv_interpreter_broken",
            severity="error",
            summary="虚拟环境解释器无法启动",
            detail=(probe.stderr or probe.stdout or "").strip(),
            components=components,
            recommended_actions=["repair_venv", "refresh_state"],
            allows_full_reinstall=True,
        )

    import_code = (
        "import json, torch, diffsynth, accelerate, peft; "
        "from transformers import Qwen3VLConfig; "
        "from torch.utils.tensorboard import SummaryWriter; "
        "print(json.dumps({'torch': torch.__version__, 'cuda': torch.version.cuda, "
        "'gpu': torch.cuda.is_available()}))"
    )
    imports = run([str(runtime.python), "-c", import_code], cwd=str(runtime.source), env=process_env(), timeout=180)
    if imports.returncode:
        components["venv"] = "broken"
        return _result(
            "venv_deps_broken",
            severity="error",
            summary="虚拟环境依赖无法导入",
            detail=(imports.stderr or imports.stdout or "").strip()[:2000],
            components=components,
            recommended_actions=["repair_venv_deps", "repair_venv", "refresh_state"],
            allows_full_reinstall=True,
        )

    try:
        import json

        facts = json.loads((imports.stdout or "").strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        facts = {"gpu": False, "cuda": None, "torch": None}

    entry = run(
        [str(runtime.python), str(runtime.source / TRAIN_SCRIPT), "--help"],
        cwd=str(runtime.source),
        env=process_env(),
        timeout=180,
    )
    if entry.returncode:
        components["source"] = "broken"
        return _result(
            "train_entry_broken",
            severity="error",
            summary="训练入口无法运行",
            detail=(entry.stderr or entry.stdout or "").strip()[:2000],
            components=components,
            recommended_actions=["repair_source", "repair_venv_deps", "refresh_state"],
            allows_full_reinstall=True,
        )

    if not facts.get("gpu"):
        return _result(
            "host_no_gpu",
            severity="warning",
            summary="未检测到 CUDA GPU，无法训练（不是仓库内环境损坏）",
            detail=f"torch={facts.get('torch')} cuda={facts.get('cuda')}",
            components=components,
            recommended_actions=[],
            allows_full_reinstall=False,
        )

    # Fingerprint / state-only issues when structure+exec are fine.
    if not runtime.state_file.exists():
        return _result(
            "state_missing",
            severity="warning",
            summary="运行时完整但状态文件缺失",
            components=components,
            recommended_actions=["refresh_state"],
            allows_full_reinstall=False,
        )

    try:
        import json

        from .extension_state import FINGERPRINT_SCHEME, fingerprint

        data = json.loads(runtime.state_file.read_text(encoding="utf-8"))
        stored = (data.get("facts") or {}).get("fingerprint")
        scheme = (data.get("facts") or {}).get("fingerprint_scheme")
        current = fingerprint(runtime)
        if stored is None or scheme != FINGERPRINT_SCHEME or stored != current:
            if data.get("state") == "ready" and stored and scheme == FINGERPRINT_SCHEME and stored != current:
                return _result(
                    "fingerprint_stale",
                    severity="error",
                    summary="环境指纹与记录不一致",
                    components=components,
                    recommended_actions=["refresh_state"],
                    allows_full_reinstall=True,
                )
            return _result(
                "fingerprint_stale",
                severity="warning",
                summary="状态指纹需要刷新",
                components=components,
                recommended_actions=["refresh_state"],
                allows_full_reinstall=False,
            )
    except Exception as exc:  # noqa: BLE001
        return _result(
            "state_unreadable",
            severity="error",
            summary="状态文件无法读取",
            detail=str(exc),
            components=components,
            recommended_actions=["refresh_state"],
            allows_full_reinstall=True,
        )

    return _result(
        "healthy",
        severity="info",
        summary="DiffSynth 运行时正常",
        components=components,
        recommended_actions=[],
        allows_full_reinstall=False,
    )


def actions_for_diagnosis(diagnosis: dict[str, Any], *, explicit: str | None = None) -> list[str]:
    """Resolve the action chain to execute."""
    if explicit == "full_reinstall":
        return ["full_reinstall"]
    if explicit:
        chain = [explicit]
        if explicit != "refresh_state" and "refresh_state" not in chain:
            chain.append("refresh_state")
        return chain
    code = diagnosis.get("code")
    if code == "missing_all":
        return ["fresh_install"]
    if code == "host_no_gpu":
        return []
    actions = list(diagnosis.get("recommended_actions") or [])
    # Auto mode: use the first non-escalation action; worker may escalate venv_deps → venv.
    if not actions:
        return []
    if actions[0] == "fresh_install":
        return actions
    # Keep progressive chain for venv_deps (deps then venv fallback handled in worker).
    return actions

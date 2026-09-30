#!/usr/bin/env python3
"""start_cloud bootstrap: 云端 slim 装机/直启一体入口的引导逻辑。

stdlib-only：跑在任何项目依赖安装之前，不得 import mikazuki。
流程（详见 docs/cloud-deploy.md）：

1. 存在完成 flag（.cloud_install_done）→ 校验指纹（python/torch/arch 硬比对）
   → 一致直启 GUI，不一致报错退出（不自动重装，换镜像是人的决策）。
2. 无 flag → 扫描候选解释器并探测 python/torch/cuda 事实 → 选最优解释器
   → 按各引擎 pack manifest 的 REQUIRES 过滤兼容引擎 → 交互选择
   （或 --engine/--yes 非交互）→ 装 GUI 依赖 + 引擎 slim 依赖 → 自检
   → 写 flag → 拉起 GUI。
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

FLAG_NAME = ".cloud_install_done"
ENV_CLOUD = "NEXT_TRAINER_CLOUD"
ENV_CLOUD_ENGINE = "NEXT_TRAINER_CLOUD_ENGINE"
GUI_PYTHON_SPEC = ">=3.10,<3.13"
DEFAULT_PORT = 6006

REPO_ROOT = Path(__file__).resolve().parents[2]

PROBE_TIMEOUT = 180
PROBE_CODE = (
    "import json, platform;"
    "d = {'python': platform.python_version(), 'arch': platform.machine(), 'torch': None, 'cuda': None, 'gpu': False};"
    "exec(\"try:\\n"
    " import torch\\n"
    " d['torch'] = torch.__version__\\n"
    " d['cuda'] = torch.version.cuda\\n"
    " d['gpu'] = bool(torch.cuda.is_available())\\n"
    "except Exception:\\n"
    " pass\");"
    "print(json.dumps(d))"
)

_SPEC_RE = re.compile(r"^\s*(==|>=|<=|!=|>|<)\s*(\S+)\s*$")


def version_key(version: str) -> tuple[int, ...]:
    """'2.8.0+cu128' -> (2, 8, 0)。本地段（+cuXXX）不参与比较。"""
    main = str(version).split("+", 1)[0]
    parts = []
    for chunk in main.split("."):
        match = re.match(r"\d+", chunk)
        parts.append(int(match.group()) if match else 0)
    return tuple(parts)


def _compare(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    length = max(len(left), len(right))
    left += (0,) * (length - len(left))
    right += (0,) * (length - len(right))
    return (left > right) - (left < right)


def spec_satisfied(version: str, spec: str) -> bool:
    """逗号分隔的版本区间（==/>=/<=/!=/>/< 子集）。空 spec 恒真。"""
    if not spec or not spec.strip():
        return True
    for part in spec.split(","):
        match = _SPEC_RE.match(part)
        if not match:
            raise ValueError(f"无法解析版本约束：{part!r}")
        op, ref = match.groups()
        cmp = _compare(version_key(version), version_key(ref))
        ok = {
            "==": cmp == 0,
            "!=": cmp != 0,
            ">=": cmp >= 0,
            "<=": cmp <= 0,
            ">": cmp > 0,
            "<": cmp < 0,
        }[op]
        if not ok:
            return False
    return True


def host_satisfies(facts: dict, requires: dict) -> bool:
    """宿主探测事实是否满足某个 pack 的 REQUIRES。"""
    if not spec_satisfied(str(facts.get("python") or "0"), str(requires.get("python") or "")):
        return False
    for key in ("torch", "cuda"):
        spec = str(requires.get(key) or "")
        if spec:
            value = facts.get(key)
            if not value or not spec_satisfied(str(value), spec):
                return False
    return True


def probe_interpreter(python: Path) -> dict | None:
    """子进程探测解释器事实；失败（无 torch / 崩溃）返回 None 或部分事实。"""
    try:
        result = subprocess.run(
            [str(python), "-c", PROBE_CODE],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PROBE_TIMEOUT,
            env={**os.environ, "PYTHONNOUSERSITE": "1"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        facts = json.loads(result.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return None
    facts["python_path"] = str(python)
    return facts


def find_candidates() -> list[Path]:
    """云端常见解释器位置：conda base/envs、PATH、系统 python。"""
    raw: list[Path] = []
    for base in (
        Path("/root/miniconda3"),
        Path("/opt/conda"),
        Path.home() / "miniconda3",
        Path.home() / "anaconda3",
    ):
        raw.append(base / "bin" / "python")
        raw.extend(sorted((base / "envs").glob("*/bin/python")) if (base / "envs").is_dir() else [])
    import shutil

    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            raw.append(Path(found))
    raw.append(Path(sys.executable))
    raw.append(Path("/usr/bin/python3"))
    raw.append(Path("/usr/local/bin/python3"))

    seen: set[str] = set()
    candidates: list[Path] = []
    for path in raw:
        try:
            if not path.is_file() or not os.access(path, os.X_OK):
                continue
            key = str(path.resolve())
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        candidates.append(path)
    return candidates


def pick_best_interpreter(probed: list[dict]) -> dict | None:
    """满足 GUI python 要求里挑最优：有 torch+GPU 优先，再按 torch/python 版本。"""
    usable = [f for f in probed if spec_satisfied(str(f.get("python") or "0"), GUI_PYTHON_SPEC)]
    if not usable:
        return None

    def rank(facts: dict):
        return (
            bool(facts.get("torch")) and bool(facts.get("gpu")),
            bool(facts.get("torch")),
            version_key(str(facts.get("torch") or "0")),
            version_key(str(facts.get("python") or "0")),
        )

    return max(usable, key=rank)


def load_pack_manifests(engines_dir: Path | None = None) -> list[dict]:
    """直接 exec 各 pack 的纯数据 manifest.py（此时项目依赖未装，不能 import）。"""
    engines_dir = engines_dir or (REPO_ROOT / "mikazuki" / "engines")
    packs = []
    for manifest_path in sorted(engines_dir.glob("*/manifest.py")):
        if manifest_path.parent.name.startswith("_"):  # _template 等样板目录
            continue
        namespace: dict = {}
        try:
            exec(compile(manifest_path.read_text(encoding="utf-8"), str(manifest_path), "exec"), namespace)
        except Exception:
            continue
        engine_id = str(namespace.get("ENGINE_ID") or "").strip()
        if not engine_id:
            continue
        packs.append(
            {
                "engine_id": engine_id,
                "requires": dict(namespace.get("REQUIRES") or {}),
                "slim_supported": bool(namespace.get("SLIM_SUPPORTED", False)),
            }
        )
    return packs


def compatible_engines(facts: dict, packs: list[dict]) -> list[dict]:
    return [p for p in packs if p["slim_supported"] and host_satisfies(facts, p["requires"])]


def read_flag(root: Path) -> dict | None:
    path = root / FLAG_NAME
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def flag_mismatch(flag: dict, facts: dict | None) -> list[str]:
    """硬比对 python/torch（含 cu 构建号）/架构。返回差异描述列表。"""
    if facts is None:
        return [f"flag 记录的解释器不可用：{flag.get('python_path')}"]
    diffs = []
    for key, label in (("python_version", "Python"), ("torch_version", "torch"), ("arch", "架构")):
        expected = flag.get(key) or ""
        actual = str(facts.get({"python_version": "python", "torch_version": "torch", "arch": "arch"}[key]) or "")
        if expected != actual:
            diffs.append(f"{label} 变化：安装时 {expected or '(无)'}，当前 {actual or '(无)'}")
    return diffs


def write_flag(root: Path, engine_id: str, facts: dict) -> Path:
    import datetime

    payload = {
        "engine": engine_id,
        "python_path": facts["python_path"],
        "python_version": facts.get("python"),
        "torch_version": facts.get("torch"),
        "cuda_version": facts.get("cuda"),
        "arch": facts.get("arch"),
        "installed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    path = root / FLAG_NAME
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _run(command: list[str], retries: int = 0) -> bool:
    attempt = 0
    while True:
        print(f"\n$ {' '.join(str(c) for c in command)}", flush=True)
        result = subprocess.run([str(c) for c in command], cwd=str(REPO_ROOT))
        if result.returncode == 0:
            return True
        attempt += 1
        if attempt > retries:
            return False
        delay = min(30, 5 * attempt)
        print(f"命令失败（exit {result.returncode}），{delay}s 后重试 {attempt}/{retries}", flush=True)
        import time

        time.sleep(delay)


def launch_gui(python: str, engine_id: str, port: int) -> None:
    env = dict(os.environ)
    env.update(
        {
            ENV_CLOUD: "1",
            ENV_CLOUD_ENGINE: engine_id,
            "HF_HOME": "huggingface",
            "PYTHONUTF8": "1",
            "PYTHONNOUSERSITE": "1",
        }
    )
    command = [
        python,
        "gui.py",
        "--port",
        str(port),
        "--listen",
        "--host",
        "0.0.0.0",
        "--skip-prepare-environment",
        "--disable-tensorboard",
    ]
    print(f"\n启动 WebUI：{' '.join(command)}", flush=True)
    os.chdir(REPO_ROOT)
    os.execvpe(python, command, env)


def _fail(message: str) -> int:
    print(f"\n[start_cloud] 失败：{message}", file=sys.stderr, flush=True)
    return 1


def _describe_facts(facts: dict) -> str:
    torch = facts.get("torch") or "未安装"
    cuda = facts.get("cuda") or "-"
    return f"{facts.get('python_path')} | python {facts.get('python')} | torch {torch} (cuda {cuda}) | {facts.get('arch')}"


def choose_engine(matched: list[dict], args: argparse.Namespace) -> dict | None:
    if args.engine:
        for pack in matched:
            if pack["engine_id"] == args.engine:
                return pack
        return None
    if not sys.stdin.isatty():
        print("[start_cloud] 非交互环境，请用 --engine <id> --yes 指定引擎", file=sys.stderr)
        return None
    print("\n宿主环境兼容以下引擎：")
    for index, pack in enumerate(matched, 1):
        requires = ", ".join(f"{k} {v}" for k, v in sorted(pack["requires"].items()))
        print(f"  [{index}] {pack['engine_id']}  （要求 {requires}）")
    while True:
        choice = input("输入要安装的引擎编号：").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(matched):
            return matched[int(choice) - 1]
        print("无效编号，请重试。")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="云端 slim 装机/直启引导")
    parser.add_argument("--engine", type=str, default=None, help="非交互指定引擎 id")
    parser.add_argument("--yes", action="store_true", help="跳过确认（配镜像打镜像用）")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)

    flag = read_flag(REPO_ROOT)
    if flag is not None:
        engine_id = str(flag.get("engine") or "")
        if args.engine and args.engine != engine_id:
            return _fail(f"本实例已按引擎 {engine_id} 装机（flag），与 --engine {args.engine} 不符；请换镜像")
        facts = probe_interpreter(Path(str(flag.get("python_path") or "")))
        diffs = flag_mismatch(flag, facts)
        if diffs:
            return _fail("环境与装机指纹不符，未重新验证：" + "；".join(diffs) + "。请换用对应镜像")
        print(f"[start_cloud] 检测到装机 flag（引擎 {engine_id}），直接启动。", flush=True)
        launch_gui(str(flag["python_path"]), engine_id, args.port)
        return 0

    print("[start_cloud] 未检测到装机 flag，进入检测安装模式。", flush=True)
    candidates = find_candidates()
    print(f"[start_cloud] 发现 {len(candidates)} 个候选解释器，逐一探测（import torch 可能较慢）...", flush=True)
    probed = [facts for facts in (probe_interpreter(c) for c in candidates) if facts]
    if not probed:
        return _fail("没有可用的 python 解释器。")
    best = pick_best_interpreter(probed)
    if best is None:
        detail = "\n".join(_describe_facts(f) for f in probed)
        return _fail(f"没有满足 GUI 要求（python {GUI_PYTHON_SPEC}）的解释器：\n{detail}")
    print(f"[start_cloud] 选定解释器：{_describe_facts(best)}", flush=True)

    packs = load_pack_manifests()
    matched = compatible_engines(best, packs)
    if not matched:
        supported = [p for p in packs if p["slim_supported"]]
        detail = "\n".join(
            f"  - {p['engine_id']}: "
            + ", ".join(f"{k} {v}" for k, v in sorted(p["requires"].items()))
            for p in supported
        )
        return _fail(
            f"宿主环境不满足任何引擎的 slim 安装要求：\n{_describe_facts(best)}\n各引擎要求：\n{detail}\n"
            "请换用带匹配 torch 的镜像。"
        )

    engine = choose_engine(matched, args)
    if engine is None:
        if args.engine:
            return _fail(f"引擎 {args.engine} 不在兼容列表内（{', '.join(p['engine_id'] for p in matched)}）")
        return _fail("未选择引擎。")
    engine_id = engine["engine_id"]
    if not args.yes and sys.stdin.isatty():
        answer = input(f"将向宿主环境 {best['python_path']} 安装 GUI 依赖与引擎 {engine_id}，继续？[y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            return _fail("用户取消。")

    python = str(best["python_path"])
    if not _run([python, "-m", "pip", "--version"]):
        return _fail(f"{python} 缺少 pip，无法安装依赖。")
    if not _run([python, "-m", "pip", "install", "-r", "requirements.txt"], retries=3):
        return _fail("GUI 依赖安装失败（requirements.txt）。")
    if not _run([python, "scripts/cloud/slim_install.py", "--engine", engine_id, "--deps-only"]):
        return _fail(f"引擎 {engine_id} slim 依赖安装失败。")
    # 引擎依赖可能顶掉 GUI 钉版，重装一遍 requirements 让 GUI 语义获胜
    if not _run([python, "-m", "pip", "install", "-r", "requirements.txt"], retries=3):
        return _fail("GUI 依赖复核安装失败（requirements.txt）。")
    if not _run([python, "scripts/cloud/slim_install.py", "--engine", engine_id, "--audit-only"]):
        return _fail(f"引擎 {engine_id} 安装自检未通过。")

    write_flag(REPO_ROOT, engine_id, best)
    print(f"[start_cloud] 装机完成，flag 已写入 {FLAG_NAME}。", flush=True)
    launch_gui(python, engine_id, args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""
Next-Trainer First-Run Environment Setup

Detects network, configures mirrors, installs GUI dependencies.
Training stacks (PyTorch, sd-scripts, ...) live in each engine pack's own
managed venv and are installed from the UI (Settings -> Training Engines).
Uses only Python stdlib -- runs before pip is available.
"""

import os
import shutil
import subprocess
import sys
import urllib.request

# ──────────────────── Configuration ────────────────────


MIRROR_PROFILES = {
    "china": {
        "label": "国内镜像 (阿里云 + 清华)",
        "pip_index_url": "https://pypi.tuna.tsinghua.edu.cn/simple",
        "pip_trusted_host": "pypi.tuna.tsinghua.edu.cn",
        "hf_endpoint": "https://hf-mirror.com",
    },
    "global": {
        "label": "Official Sources",
        "pip_index_url": None,
        "pip_trusted_host": None,
        "hf_endpoint": None,
    },
}

DISK_SPACE_REQUIRED_GB = 2

# ──────────────────── Path helpers ────────────────────


def _base_dir():
    """Portable package root (parent of Next-Trainer/)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _python_exe():
    return os.path.join(_base_dir(), "python_embeded", "python.exe")


def _get_pip_path():
    return os.path.join(_base_dir(), "python_embeded", "get-pip.py")


def _sd_trainer_dir():
    return os.path.dirname(os.path.abspath(__file__))


# ──────────────────── UI helpers ────────────────────

_TOTAL_STEPS = 4


def _banner():
    w = 50
    print()
    print("╔" + "═" * w + "╗")
    print("║" + "Next-Trainer 环境安装向导".center(w - 6) + "║")
    print("╚" + "═" * w + "╝")
    print()


def _step(n, msg, end="\n"):
    print(f"  [{n}/{_TOTAL_STEPS}] {msg}", end=end, flush=True)


def _ok(msg="完成"):
    print(f"  >>> {msg}")


def _fail(msg):
    print(f"\n  [!] {msg}")


def _separator():
    print("  " + "─" * 48)


# ──────────────────── Core logic ────────────────────


def _missing_requirements():
    """Return requirement specs from requirements.txt that are not installed.

    Uses the embedded interpreter's own pip metadata so the check matches what
    install_requirements would actually install. Triton-windows is skipped to
    stay consistent with _filter_requirements.
    """
    req_file = os.path.join(_sd_trainer_dir(), "requirements.txt")
    if not os.path.isfile(req_file):
        return []

    check_src = (
        "import sys\n"
        "try:\n"
        "    from importlib.metadata import distributions\n"
        "except Exception:\n"
        "    print('CHECK_UNAVAILABLE'); sys.exit(0)\n"
        "import re\n"
        "skip = {'triton-windows', 'triton'}\n"
        "installed = set()\n"
        "for dist in distributions():\n"
        "    name = (dist.metadata['Name'] or '').strip().lower().replace('_', '-')\n"
        "    if name:\n"
        "        installed.add(name)\n"
        "missing = []\n"
        "with open(sys.argv[1], 'r', encoding='utf-8-sig') as f:\n"
        "    for raw in f:\n"
        "        line = raw.strip()\n"
        "        if not line or line.startswith('#') or line.startswith('-'):\n"
        "            continue\n"
        "        if '# skip_verify' in line:\n"
        "            continue\n"
        "        spec = line.split('#', 1)[0].strip()\n"
        "        if ';' in spec:\n"
        "            cond = spec.split(';', 1)[1]\n"
        "            if 'win32' in cond and sys.platform != 'win32':\n"
        "                continue\n"
        "            if 'linux' in cond and sys.platform != 'linux':\n"
        "                continue\n"
        "            spec = spec.split(';', 1)[0].strip()\n"
        "        name = re.split(r'[<>=!~\\[ ]', spec, 1)[0].strip().lower().replace('_', '-')\n"
        "        if not name or name in skip:\n"
        "            continue\n"
        "        if name not in installed:\n"
        "            missing.append(name)\n"
        "for m in missing:\n"
        "    print(m)\n"
    )
    try:
        result = subprocess.run(
            [_python_exe(), "-s", "-c", check_src, req_file],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "PYTHONNOUSERSITE": "1"},
        )
    except Exception:
        return []
    out = (result.stdout or "").strip()
    if not out or "CHECK_UNAVAILABLE" in out:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


GUI_CORE_MODULES = ("fastapi", "onnxruntime", "cv2", "tensorboard")


def check_already_installed(quiet=False):
    """Return True only when core runtime deps are importable AND every
    requirements.txt package is present. A missing requirement (e.g. a newly
    added onnxruntime-gpu after an update) triggers the repair install path."""
    def _say(msg):
        if not quiet:
            print(msg)

    for module in GUI_CORE_MODULES:
        try:
            __import__(module)
        except Exception as exc:
            _say(f"  检测到依赖不完整，将执行修复安装：{module} ({exc})")
            return False

    missing = _missing_requirements()
    if missing:
        preview = ", ".join(missing[:8]) + (" ..." if len(missing) > 8 else "")
        _say(f"  检测到缺失的依赖，将执行补装：{preview}")
        return False

    return True


def check_disk_space():
    total, _used, free = shutil.disk_usage(_base_dir())
    free_gb = free / (1024 ** 3)
    if free_gb < DISK_SPACE_REQUIRED_GB:
        _fail(f"磁盘空间不足: 可用 {free_gb:.1f} GB，需要至少 {DISK_SPACE_REQUIRED_GB} GB")
        return False
    return True


def detect_gpu():
    """Detect GPU vendor via WMI. Returns 'nvidia', 'amd', or 'unknown'."""
    try:
        result = subprocess.run(
            ["wmic", "path", "Win32_VideoController", "get", "Name"],
            capture_output=True, text=True, timeout=10,
        )
        output = result.stdout.lower()
        has_nvidia = "nvidia" in output or "geforce" in output or "rtx" in output
        has_amd = "amd" in output or "radeon" in output
        if has_nvidia:
            return "nvidia"
        if has_amd:
            return "amd"
    except Exception:
        pass
    return "unknown"


def detect_network():
    """Quick connectivity probe: if Google is reachable we're outside China."""
    try:
        urllib.request.urlopen("https://www.google.com", timeout=3)
        return "global"
    except Exception:
        return "china"


def _run_pip(args):
    """Run a pip command, letting output stream to the console."""
    cmd = [_python_exe(), "-s", "-m", "pip"] + args
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PIP_NO_COLOR"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    return subprocess.call(cmd, env=env) == 0


def install_pip():
    get_pip = _get_pip_path()
    if not os.path.exists(get_pip):
        url = "https://bootstrap.pypa.io/get-pip.py"
        urllib.request.urlretrieve(url, get_pip)

    env = os.environ.copy()
    env["PYTHONNOUSERSITE"] = "1"
    return subprocess.call(
        [_python_exe(), "-s", get_pip, "--no-warn-script-location", "-q"],
        env=env,
    ) == 0


def _filter_requirements(req_file):
    """Read requirements.txt, filtering out packages incompatible with embedded Python."""
    skip_packages = {"triton-windows", "triton"}
    filtered_path = req_file + ".filtered"
    with open(req_file, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()
    with open(filtered_path, "w", encoding="utf-8") as f:
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                pkg_name = stripped.split("<")[0].split(">")[0].split("=")[0].split(";")[0].strip()
                if pkg_name.lower() in skip_packages:
                    f.write(f"# [portable skip] {line}")
                    continue
            f.write(line)
    return filtered_path


def install_requirements(region):
    cfg = MIRROR_PROFILES[region]
    req_file = os.path.join(_sd_trainer_dir(), "requirements.txt")
    filtered_req = _filter_requirements(req_file)
    args = ["install", "-r", filtered_req, "--no-warn-script-location"]
    if region == "china" and cfg.get("pip_index_url"):
        args += ["-i", cfg["pip_index_url"]]
        if cfg.get("pip_trusted_host"):
            args += ["--trusted-host", cfg["pip_trusted_host"]]
    ok = _run_pip(args)
    try:
        os.remove(filtered_req)
    except OSError:
        pass
    return ok


def write_mirror_env(region):
    """Persist mirror settings so subsequent launches use them too."""
    cfg = MIRROR_PROFILES[region]
    if cfg.get("hf_endpoint"):
        os.environ["HF_ENDPOINT"] = cfg["hf_endpoint"]
    if cfg.get("pip_index_url"):
        os.environ["PIP_INDEX_URL"] = cfg["pip_index_url"]


# ──────────────────── Main ────────────────────


def _core_modules_ok():
    for module in GUI_CORE_MODULES:
        try:
            __import__(module)
        except Exception:
            return False
    return True


def repair_requirements_only():
    """Fast path: core deps already present, only requirements.txt has
    new/missing packages (e.g. onnxruntime-gpu added by an update). Install
    just the requirements."""
    _banner()
    region = detect_network()
    if region == "china":
        print("  检测到缺失依赖，使用国内镜像补装组件...")
    else:
        print("  检测到缺失依赖，补装组件...")
    write_mirror_env(region)
    if not install_requirements(region):
        _fail("依赖补装失败，请检查网络连接后重新运行 run_gui.bat")
        return 1
    _ok("依赖补装完成")
    return 0


def main():
    _banner()

    if check_already_installed():
        print("  环境已安装，跳过安装步骤。")
        return 0

    # Lightweight repair: core deps are fine, only some
    # requirements.txt packages are missing.
    if _core_modules_ok() and _missing_requirements():
        return repair_requirements_only()

    # GPU check — warn AMD users early
    gpu = detect_gpu()
    if gpu == "amd":
        print("  ╔══════════════════════════════════════════════╗")
        print("  ║          检测到 AMD 显卡 (Radeon)            ║")
        print("  ╠══════════════════════════════════════════════╣")
        print("  ║  当前版本仅支持 NVIDIA GPU 进行训练。        ║")
        print("  ║  AMD GPU (ROCm) 支持正在开发中，敬请期待！  ║")
        print("  ║                                              ║")
        print("  ║  Linux 用户可参考 ROCm 方案:                 ║")
        print("  ║  https://rocm.docs.amd.com                   ║")
        print("  ╚══════════════════════════════════════════════╝")
        print()
        try:
            input("  按回车键退出，或等待 AMD 支持后再试...")
        except EOFError:
            pass
        return 1

    if not check_disk_space():
        return 1

    # 1 — Network detection
    _step(1, "检测网络环境...", end="")
    region = detect_network()
    if region == "china":
        print(" 国内网络，已启用镜像加速")
    else:
        print(" 国际网络")
    write_mirror_env(region)

    # 2 — pip
    _step(2, "安装 pip 包管理器...", end="")
    if not install_pip():
        _fail("pip 安装失败")
        return 1
    print(" 完成")

    # 3 — requirements
    _separator()
    _step(3, "安装 GUI 组件 (fastapi, onnxruntime ...)")
    print()
    if not install_requirements(region):
        _fail("组件安装失败，请检查网络连接后重新运行 run_gui.bat")
        return 1
    _ok("组件安装完成")

    print()
    print("  ══════════════════════════════════════════════")
    print("    环境安装完成！正在启动 Next-Trainer...")
    print("  ══════════════════════════════════════════════")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

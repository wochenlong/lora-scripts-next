# -*- coding: utf-8 -*-
"""
SD-Trainer First-Run Environment Setup

Detects network, configures mirrors, installs PyTorch + dependencies.
Uses only Python stdlib -- runs before pip is available.
"""

import locale
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

# ──────────────────── Configuration ────────────────────

TORCH_VERSION = "2.7.0"
TORCHVISION_VERSION = "0.22.0"
CUDA_TAG = "cu128"
PYTHON_TAG = "cp310"
PLATFORM_TAG = "win_amd64"
TORCH_WHEEL_NAME = (
    f"torch-{TORCH_VERSION}+{CUDA_TAG}-{PYTHON_TAG}-{PYTHON_TAG}-{PLATFORM_TAG}.whl"
)
PROBE_BYTES = 32 * 1024 * 1024
PROBE_MAX_SECONDS = 15

MIRROR_PROFILES = {
    "china": {
        "label": "国内镜像 (阿里云 + 清华)",
        "torch_find_links": f"https://mirrors.aliyun.com/pytorch-wheels/{CUDA_TAG}/",
        "pip_index_url": "https://pypi.tuna.tsinghua.edu.cn/simple",
        "pip_trusted_host": "pypi.tuna.tsinghua.edu.cn",
        "hf_endpoint": "https://hf-mirror.com",
    },
    "global": {
        "label": "Official Sources",
        "torch_index_url": f"https://download.pytorch.org/whl/{CUDA_TAG}",
        "pip_index_url": None,
        "pip_trusted_host": None,
        "hf_endpoint": None,
    },
}

PYTORCH_SOURCES = [
    {
        "label": "阿里云 PyTorch Wheels",
        "mode": "find-links",
        "url": f"https://mirrors.aliyun.com/pytorch-wheels/{CUDA_TAG}/",
    },
    {
        "label": "SJTUG PyTorch Wheels",
        "mode": "index-url",
        "url": f"https://mirror.sjtu.edu.cn/pytorch-wheels/{CUDA_TAG}",
    },
    {
        "label": "PyTorch Official",
        "mode": "index-url",
        "url": f"https://download.pytorch.org/whl/{CUDA_TAG}",
    },
]

DISK_SPACE_REQUIRED_GB = 7

# ──────────────────── Path helpers ────────────────────


def _base_dir():
    """Portable package root (parent of SD-Trainer/)."""
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
    print("║" + "SD-Trainer 环境安装向导".center(w - 6) + "║")
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


def check_already_installed():
    """Return True only when core runtime deps are importable."""
    torch_dir = os.path.join(
        _base_dir(), "python_embeded", "Lib", "site-packages", "torch"
    )
    if not os.path.isdir(torch_dir):
        return False

    core_modules = ("torch", "torchvision", "accelerate", "diffusers", "gradio")
    for module in core_modules:
        try:
            __import__(module)
        except Exception as exc:
            print(f"  检测到依赖不完整，将执行修复安装：{module} ({exc})")
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


def _join_wheel_url(base_url):
    return base_url.rstrip("/") + "/" + urllib.parse.quote(TORCH_WHEEL_NAME, safe="")


def _probe_url(source, timeout=15):
    # Measure real wheel throughput instead of only first-byte latency. Some
    # mirrors respond quickly but download large wheels very slowly.
    t0 = time.perf_counter()
    wheel_url = _join_wheel_url(source["url"])
    request = urllib.request.Request(
        wheel_url,
        headers={
            "User-Agent": "SD-Trainer installer",
            "Range": f"bytes=0-{PROBE_BYTES - 1}",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = getattr(response, "status", 200)
        if status >= 400:
            raise OSError(f"HTTP {status}")
        bytes_read = 0
        while (
            bytes_read < PROBE_BYTES
            and time.perf_counter() - t0 < PROBE_MAX_SECONDS
        ):
            chunk = response.read(min(1024 * 1024, PROBE_BYTES - bytes_read))
            if not chunk:
                break
            bytes_read += len(chunk)

    elapsed = max(time.perf_counter() - t0, 0.001)
    if bytes_read <= 0:
        raise OSError("empty response")
    return {
        **source,
        "elapsed": elapsed,
        "bytes_read": bytes_read,
        "mbps": bytes_read / elapsed / (1024 * 1024),
    }


def probe_pytorch_sources():
    """Probe PyTorch wheel sources concurrently and return them by speed."""
    print("  正在测速 PyTorch 下载源...")
    results = []
    with ThreadPoolExecutor(max_workers=len(PYTORCH_SOURCES)) as executor:
        futures = {
            executor.submit(_probe_url, source): source
            for source in PYTORCH_SOURCES
        }
        for future in as_completed(futures):
            source = futures[future]
            try:
                result = future.result()
                results.append(result)
                print(
                    f"    OK   {result['label']} "
                    f"({result['mbps']:.1f} MB/s, {result['elapsed']:.2f}s)"
                )
            except Exception as exc:
                print(f"    FAIL {source['label']} ({exc})")

    if not results:
        return []

    results.sort(key=lambda item: (-item["mbps"], item["elapsed"]))
    print(f"  已选择最快源: {results[0]['label']}")
    return results


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


def install_torch(_region):
    sources = probe_pytorch_sources()
    if not sources:
        _fail("所有 PyTorch 下载源均无法连接，请检查网络或代理设置后重试")
        return False

    for index, source in enumerate(sources):
        if index:
            print(f"  正在尝试备用源: {source['label']}")
        args = [
            "install",
            f"torch=={TORCH_VERSION}+{CUDA_TAG}",
            f"torchvision=={TORCHVISION_VERSION}+{CUDA_TAG}",
            "--no-warn-script-location",
        ]
        if source["mode"] == "find-links":
            args += ["-f", source["url"]]
        else:
            args += ["--index-url", source["url"]]
        if _run_pip(args):
            return True

    _fail("所有可连接的 PyTorch 下载源均安装失败，请检查网络、代理或 pip 输出后重试")
    return False


def _filter_requirements(req_file):
    """Read requirements.txt, filtering out packages incompatible with embedded Python."""
    skip_packages = {"triton-windows", "triton"}
    filtered_path = req_file + ".filtered"
    with open(req_file, "r", encoding="utf-8") as f:
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


def verify_installation():
    """Quick smoke test."""
    result = subprocess.run(
        [_python_exe(), "-s", "-c",
         "import torch; print(f'PyTorch {torch.__version__}  CUDA {torch.version.cuda}')"],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "PYTHONNOUSERSITE": "1"},
    )
    if result.returncode == 0:
        _ok(result.stdout.strip())
        return True
    _fail("PyTorch 验证失败")
    return False


# ──────────────────── Main ────────────────────


def main():
    _banner()

    if check_already_installed():
        print("  环境已安装，跳过安装步骤。")
        return 0

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

    # 3 — PyTorch
    _separator()
    _step(3, f"安装 PyTorch {TORCH_VERSION} (CUDA 12.8)")
    print(f"       下载约 3 GB，请耐心等待...\n")
    t0 = time.time()
    if not install_torch(region):
        _fail("PyTorch 安装失败，请检查网络连接后重新运行 run_gui.bat")
        return 1
    elapsed = time.time() - t0
    _ok(f"PyTorch 安装完成 ({elapsed:.0f}s)")

    # 4 — requirements
    _separator()
    _step(4, "安装训练组件 (transformers, diffusers, gradio ...)")
    print()
    if not install_requirements(region):
        _fail("训练组件安装失败，请检查网络连接后重新运行 run_gui.bat")
        return 1
    _ok("训练组件安装完成")

    # Verify
    _separator()
    print("  验证安装...")
    if not verify_installation():
        return 1

    print()
    print("  ══════════════════════════════════════════════")
    print("    环境安装完成！正在启动 SD-Trainer...")
    print("  ══════════════════════════════════════════════")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

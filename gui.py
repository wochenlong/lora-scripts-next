import argparse
import locale
import os
import platform
import subprocess
import sys

from mikazuki.launch_utils import (base_dir_path, catch_exception, git_tag,
                                   prepare_environment, check_port_avaliable)
from mikazuki.log import log
from mikazuki.portable_utils import sanitize_embedded_deps, train_env_overrides

parser = argparse.ArgumentParser(description="GUI for stable diffusion training")
parser.add_argument("--host", type=str, default="127.0.0.1")
parser.add_argument("--port", type=int, default=28000, help="Port to run the server on")
parser.add_argument("--listen", action="store_true")
parser.add_argument("--skip-prepare-environment", action="store_true")
parser.add_argument("--skip-prepare-onnxruntime", action="store_true")
parser.add_argument("--disable-tensorboard", action="store_true", default=False)
parser.add_argument("--disable-tageditor", action="store_true")
parser.add_argument(
    "--enable-legacy-tageditor",
    action="store_true",
    help="Start the legacy Gradio Dataset Tag Editor compatibility service.",
)
parser.add_argument("--disable-train-monitor", action="store_true")
parser.add_argument("--disable-auto-mirror", action="store_true")
parser.add_argument("--tensorboard-host", type=str, default="127.0.0.1", help="Port to run the tensorboard")
parser.add_argument("--tensorboard-port", type=int, default=6006, help="Port to run the tensorboard")
parser.add_argument("--train-monitor-port", type=int, default=6008, help="Port to run the train status monitor")
parser.add_argument("--localization", type=str)
parser.add_argument("--browser", type=str, default=None,
                    choices=["chrome", "edge", "default"],
                    help="Browser to open GUI: chrome, edge, or default (system default)")
parser.add_argument("--dev", action="store_true")


def ensure_port_available(
    port: int,
    fallback_start: int,
    fallback_end: int,
    label: str,
    reserved_ports: set[int],
    preferred_reserved_port: int | None = None,
) -> int:
    if (port == preferred_reserved_port or port not in reserved_ports) and check_port_avaliable(port):
        reserved_ports.add(port)
        return port

    for candidate in range(fallback_start, fallback_end):
        if candidate in reserved_ports and candidate != preferred_reserved_port:
            continue
        if check_port_avaliable(candidate):
            reserved_ports.add(candidate)
            log.warning(f"{label} port {port} is already in use, using {candidate} instead.")
            return candidate

    log.error(f"{label}: no available port in range {fallback_start}-{fallback_end}.")
    return port


@catch_exception
def run_train_monitor():
    env = os.environ.copy()
    subprocess.Popen([sys.executable, str(base_dir_path() / "train_monitor" / "server.py")], env=env)


@catch_exception
def run_tensorboard():
    log.info("Starting tensorboard...")
    subprocess.Popen([sys.executable, "-m", "tensorboard.main", "--logdir", "logs",
                     "--host", args.tensorboard_host, "--port", str(args.tensorboard_port)])


@catch_exception
def run_tag_editor(port: int):
    scripts_dir = base_dir_path() / "mikazuki" / "dataset-tag-editor" / "scripts"
    launch_script = scripts_dir / "launch.py"
    if not launch_script.exists():
        log.warning(
            "Dataset Tag Editor not found (submodule not initialized). "
            "Attempting to initialize... / "
            "标签编辑器未找到（子模块未初始化），正在尝试自动初始化..."
        )
        try:
            subprocess.run(
                ["git", "submodule", "update", "--init", "--depth=1", "--", "mikazuki/dataset-tag-editor"],
                cwd=str(base_dir_path()), timeout=120, check=False,
            )
        except Exception as e:
            log.warning(f"Auto-init submodule failed: {e}")
        if not launch_script.exists():
            log.error(
                "Dataset Tag Editor still not available after init attempt. "
                "Please run 'git submodule update --init' manually. / "
                "自动初始化失败，请手动执行 git submodule update --init。"
            )
            return
    log.info("Starting tageditor...")
    tag_args = [
        "--port", str(port),
        "--shadow-gradio-output",
        "--root-path", "/proxy/tageditor"
    ]
    if args.localization:
        tag_args.extend(["--localization", args.localization])
    else:
        l = locale.getdefaultlocale()[0]
        if l and l.startswith("zh"):
            tag_args.extend(["--localization", "zh-Hans"])
    bootstrap = (
        "import sys;"
        f"sys.path.insert(0, {str(scripts_dir)!r});"
        f"sys.argv = [{str(launch_script)!r}] + {tag_args!r};"
        f"exec(compile(open({str(launch_script)!r}).read(), {str(launch_script)!r}, 'exec'))"
    )
    subprocess.Popen([sys.executable, "-s", "-c", bootstrap])


def launch():
    sanitize_embedded_deps(log.warning)
    for key, value in train_env_overrides().items():
        os.environ.setdefault(key, value)
    log.info("Starting SD-Trainer Mikazuki GUI...")
    log.info(f"Base directory: {base_dir_path()}, Working directory: {os.getcwd()}")
    log.info(f"{platform.system()} Python {platform.python_version()} {sys.executable}")
    legacy_tageditor_enabled = args.enable_legacy_tageditor and not args.disable_tageditor

    if not args.skip_prepare_environment:
        prepare_environment(disable_auto_mirror=args.disable_auto_mirror)

    # Protect each service's default port before scanning fallbacks. Otherwise
    # TensorBoard can claim 6008 as a fallback and make monitor links open it.
    protected_default_ports = {args.port}
    if legacy_tageditor_enabled:
        protected_default_ports.add(28001)
    if not args.disable_tensorboard:
        protected_default_ports.add(args.tensorboard_port)
    if not args.disable_train_monitor:
        protected_default_ports.add(args.train_monitor_port)

    reserved_ports: set[int] = set(protected_default_ports)
    tageditor_port = 28001
    if legacy_tageditor_enabled:
        tageditor_port = ensure_port_available(
            28001, 28001, 28020, "Tag editor", reserved_ports, preferred_reserved_port=28001
        )
    args.port = ensure_port_available(
        args.port, args.port, args.port + 20, "GUI", reserved_ports, preferred_reserved_port=args.port
    )
    if not args.disable_tensorboard:
        args.tensorboard_port = ensure_port_available(
            args.tensorboard_port,
            args.tensorboard_port,
            args.tensorboard_port + 20,
            "TensorBoard",
            reserved_ports,
            preferred_reserved_port=args.tensorboard_port,
        )
    if not args.disable_train_monitor:
        args.train_monitor_port = ensure_port_available(
            args.train_monitor_port,
            args.train_monitor_port,
            args.train_monitor_port + 20,
            "Train monitor",
            reserved_ports,
            preferred_reserved_port=args.train_monitor_port,
        )

    from mikazuki.update_check import local_version
    log.info(f"SD-Trainer Version: {local_version()}")

    os.environ["MIKAZUKI_HOST"] = args.host
    os.environ["MIKAZUKI_PORT"] = str(args.port)
    os.environ["MIKAZUKI_TENSORBOARD_HOST"] = args.tensorboard_host
    os.environ["MIKAZUKI_TENSORBOARD_PORT"] = str(args.tensorboard_port)
    os.environ["TRAIN_MONITOR_PORT"] = str(args.train_monitor_port)
    os.environ["MIKAZUKI_TAGEDITOR_PORT"] = str(tageditor_port)
    os.environ["MIKAZUKI_DEV"] = "1" if args.dev else "0"
    if args.browser:
        os.environ["MIKAZUKI_BROWSER"] = args.browser

    if args.listen:
        args.host = "0.0.0.0"
        args.tensorboard_host = "0.0.0.0"

    if legacy_tageditor_enabled:
        run_tag_editor(tageditor_port)
    else:
        log.info("Using native dataset editor at /dataset-editor.html; legacy Gradio tag editor is disabled.")

    if not args.disable_tensorboard:
        run_tensorboard()

    if not args.disable_train_monitor:
        run_train_monitor()

    import uvicorn
    log.info(f"Server started at http://{args.host}:{args.port}")
    log.info(f"Train monitor at http://{args.host}:{args.train_monitor_port}")
    uvicorn.run("mikazuki.app:app", host=args.host, port=args.port, log_level="error", reload=args.dev)


if __name__ == "__main__":
    args, _ = parser.parse_known_args()
    launch()

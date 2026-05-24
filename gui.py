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
parser.add_argument("--disable-train-monitor", action="store_true")
parser.add_argument("--disable-auto-mirror", action="store_true")
parser.add_argument("--tensorboard-host", type=str, default="127.0.0.1", help="Port to run the tensorboard")
parser.add_argument("--tensorboard-port", type=int, default=6006, help="Port to run the tensorboard")
parser.add_argument("--train-monitor-port", type=int, default=6008, help="Port to run the train status monitor")
parser.add_argument("--tageditor-port", type=int, default=28001, help="Port to run the dataset tag editor")
parser.add_argument("--localization", type=str)
parser.add_argument("--browser", type=str, default=None,
                    choices=["chrome", "edge", "default"],
                    help="Browser to open GUI: chrome, edge, or default (system default)")
parser.add_argument("--dev", action="store_true")


def ensure_port_available(port: int, fallback_start: int, fallback_end: int, label: str, reserved_ports: set[int]) -> int:
    if port not in reserved_ports and check_port_avaliable(port):
        reserved_ports.add(port)
        return port

    for candidate in range(fallback_start, fallback_end):
        if candidate in reserved_ports:
            continue
        if check_port_avaliable(candidate):
            reserved_ports.add(candidate)
            log.warning(f"{label} port {port} is already in use, using {candidate} instead.")
            return candidate

    log.error(f"{label} port finding fallback error")
    return port


@catch_exception
def run_train_monitor():
    log.info(f"Starting train status monitor on port {args.train_monitor_port}...")
    env = os.environ.copy()
    env["TRAIN_MONITOR_PORT"] = str(args.train_monitor_port)
    subprocess.Popen([sys.executable, str(base_dir_path() / "train_monitor" / "server.py")], env=env)


@catch_exception
def run_tensorboard():
    log.info("Starting tensorboard...")
    subprocess.Popen([sys.executable, "-m", "tensorboard.main", "--logdir", "logs",
                     "--host", args.tensorboard_host, "--port", str(args.tensorboard_port)])


@catch_exception
def run_tag_editor(port: int):
    log.info(f"Starting tageditor on port {port}...")
    cmd = [
        sys.executable,
        base_dir_path() / "mikazuki/dataset-tag-editor/scripts/launch.py",
        "--port", str(port),
        "--shadow-gradio-output",
        "--root-path", "/proxy/tageditor"
    ]
    if args.localization:
        cmd.extend(["--localization", args.localization])
    else:
        l = locale.getdefaultlocale()[0]
        if l and l.startswith("zh"):
            cmd.extend(["--localization", "zh-Hans"])
    subprocess.Popen(cmd)


def launch():
    sanitize_embedded_deps(log.warning)
    for key, value in train_env_overrides().items():
        os.environ.setdefault(key, value)
    log.info("Starting SD-Trainer Mikazuki GUI...")
    log.info(f"Base directory: {base_dir_path()}, Working directory: {os.getcwd()}")
    log.info(f"{platform.system()} Python {platform.python_version()} {sys.executable}")

    if not args.skip_prepare_environment:
        prepare_environment(disable_auto_mirror=args.disable_auto_mirror)

    # Keep fallback ports near their defaults and reserve chosen ports so two
    # child services cannot both fall back to the same port before they start.
    reserved_ports: set[int] = set()
    if not args.disable_tageditor:
        args.tageditor_port = ensure_port_available(
            args.tageditor_port, args.tageditor_port, args.tageditor_port + 20, "Tag editor", reserved_ports)
    args.port = ensure_port_available(args.port, args.port, args.port + 20, "GUI", reserved_ports)
    if not args.disable_tensorboard:
        args.tensorboard_port = ensure_port_available(
            args.tensorboard_port, args.tensorboard_port, args.tensorboard_port + 20, "TensorBoard", reserved_ports)
    if not args.disable_train_monitor:
        args.train_monitor_port = ensure_port_available(
            args.train_monitor_port, args.train_monitor_port, args.train_monitor_port + 20, "Train monitor", reserved_ports)

    from mikazuki.update_check import local_version
    log.info(f"SD-Trainer Version: {local_version()}")

    os.environ["MIKAZUKI_HOST"] = args.host
    os.environ["MIKAZUKI_PORT"] = str(args.port)
    os.environ["MIKAZUKI_TENSORBOARD_HOST"] = args.tensorboard_host
    os.environ["MIKAZUKI_TENSORBOARD_PORT"] = str(args.tensorboard_port)
    os.environ["TRAIN_MONITOR_PORT"] = str(args.train_monitor_port)
    os.environ["MIKAZUKI_TAGEDITOR_PORT"] = str(args.tageditor_port)
    os.environ["MIKAZUKI_DEV"] = "1" if args.dev else "0"
    if args.browser:
        os.environ["MIKAZUKI_BROWSER"] = args.browser

    if args.listen:
        args.host = "0.0.0.0"
        args.tensorboard_host = "0.0.0.0"

    if not args.disable_tageditor:
        run_tag_editor(args.tageditor_port)

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

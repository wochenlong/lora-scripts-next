import argparse
import os
import platform
import subprocess
import sys
import time

from mikazuki.launch_utils import (base_dir_path, catch_exception, git_tag,
                                   prepare_environment,
                                   ensure_requirements_installed)
from mikazuki.log import log
from mikazuki.portable_utils import sanitize_embedded_deps, train_env_overrides
from mikazuki.startup_settings import read_startup_settings, resolve_startup

parser = argparse.ArgumentParser(description="GUI for stable diffusion training")
parser.add_argument("--host", type=str, default=None)
parser.add_argument("--port", type=int, default=None, help="Port to run the server on")
parser.add_argument("--listen", action="store_true")
parser.add_argument("--skip-prepare-environment", action="store_true")
parser.add_argument("--skip-prepare-onnxruntime", action="store_true")
tb_flags = parser.add_mutually_exclusive_group()
tb_flags.add_argument("--disable-tensorboard", action="store_true", default=None)
tb_flags.add_argument("--enable-tensorboard", dest="disable_tensorboard", action="store_false")
monitor_flags = parser.add_mutually_exclusive_group()
monitor_flags.add_argument("--disable-train-monitor", action="store_true", default=None)
monitor_flags.add_argument("--enable-train-monitor", dest="disable_train_monitor", action="store_false")
parser.add_argument("--disable-auto-mirror", action="store_true")
parser.add_argument("--tensorboard-host", type=str, default=None, help="Host to run the tensorboard")
parser.add_argument("--tensorboard-port", type=int, default=None,
                    help="TensorBoard port; enables TensorBoard unless --disable-tensorboard is set")
parser.add_argument("--train-monitor-port", type=int, default=None, help="Port to run the train status monitor")
parser.add_argument("--port-conflict", choices=["error", "next_available"])
parser.add_argument("--tensorboard-port-conflict", choices=["error", "disable", "next_available"])
parser.add_argument("--train-monitor-port-conflict", choices=["error", "disable", "next_available"])
browser_flags = parser.add_mutually_exclusive_group()
browser_flags.add_argument("--open-browser", action="store_true", default=None)
browser_flags.add_argument("--no-open-browser", dest="open_browser", action="store_false")
parser.add_argument("--localization", type=str)
parser.add_argument("--browser", type=str, default=None,
                    choices=["chrome", "edge", "default"],
                    help="Browser to open GUI: chrome, edge, or default (system default)")
parser.add_argument("--dev", action="store_true")


def _popen(command: list[str], **kwargs) -> subprocess.Popen:
    if sys.platform.startswith("linux"):
        command = [
            sys.executable,
            str(base_dir_path() / "mikazuki" / "child_process.py"),
            str(os.getpid()),
            *command,
        ]
    return subprocess.Popen(command, **kwargs)


@catch_exception
def run_train_monitor():
    env = os.environ.copy()
    return _popen([sys.executable, str(base_dir_path() / "train_monitor" / "server.py")], env=env)


@catch_exception
def run_tensorboard():
    log.info("Starting tensorboard...")
    return _popen([sys.executable, "-m", "tensorboard.main", "--logdir", "logs",
                   "--host", args.tensorboard_host, "--port", str(args.tensorboard_port)])


def stop_child_processes(
    processes: list[tuple[str, subprocess.Popen]], timeout: float = 5.0
) -> None:
    running = []
    for name, process in processes:
        try:
            if process.poll() is None:
                running.append((name, process))
        except Exception as e:
            log.warning(f"Could not inspect {name} process: {e}")
    if not running:
        return

    for name, process in running:
        log.info(f"Stopping {name} (PID {process.pid})...")
        try:
            process.terminate()
        except Exception as e:
            log.warning(f"Could not terminate {name} (PID {process.pid}): {e}")

    deadline = time.monotonic() + timeout
    remaining = []
    for name, process in running:
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            remaining.append((name, process))
        except Exception as e:
            log.warning(f"Could not wait for {name} (PID {process.pid}): {e}")
            remaining.append((name, process))

    for name, process in remaining:
        log.warning(f"{name} did not stop in time; killing PID {process.pid}.")
        try:
            process.kill()
        except ProcessLookupError:
            continue
        except Exception as e:
            log.warning(f"Could not kill {name} (PID {process.pid}): {e}")
            continue
        try:
            process.wait()
        except Exception as e:
            log.warning(f"Could not reap {name} (PID {process.pid}): {e}")


def launch():
    startup = resolve_startup(read_startup_settings(), args)
    sanitize_embedded_deps(log.warning)
    from mikazuki.china_hub import enable_china_hub

    if enable_china_hub():
        log.info("Using ModelScope hub patch for Hugging Face downloads (国内下载走魔搭)")
    for key, value in train_env_overrides().items():
        os.environ.setdefault(key, value)
    log.info("Starting SD-Trainer Mikazuki GUI...")
    log.info(f"Base directory: {base_dir_path()}, Working directory: {os.getcwd()}")
    log.info(f"{platform.system()} Python {platform.python_version()} {sys.executable}")

    if not args.skip_prepare_environment:
        prepare_environment(disable_auto_mirror=args.disable_auto_mirror,
                            prepare_onnxruntime=not args.skip_prepare_onnxruntime)
    else:
        # Portable launch skips prepare_environment, so requirements.txt is
        # otherwise never validated. Run a cheap presence-only guard so newly
        # added or missing packages (e.g. onnxruntime-gpu) get repaired instead
        # of silently breaking tagging/training.
        ensure_requirements_installed("requirements.txt")

    args.host, args.port = startup.gui.host, startup.gui.port
    args.tensorboard_host, args.tensorboard_port = startup.tensorboard.host, startup.tensorboard.port
    args.train_monitor_port = startup.monitor.port
    args.disable_tensorboard = not startup.tensorboard.enabled
    args.disable_train_monitor = not startup.monitor.enabled

    from mikazuki.update_check import local_version
    log.info(f"SD-Trainer Version: {local_version()}")

    os.environ["MIKAZUKI_HOST"] = args.host
    os.environ["MIKAZUKI_PORT"] = str(args.port)
    os.environ["MIKAZUKI_TENSORBOARD_HOST"] = args.tensorboard_host
    os.environ["MIKAZUKI_TENSORBOARD_PORT"] = str(args.tensorboard_port)
    os.environ["MIKAZUKI_TENSORBOARD_ENABLED"] = "0" if args.disable_tensorboard else "1"
    os.environ["TRAIN_MONITOR_HOST"] = startup.monitor.host
    os.environ["TRAIN_MONITOR_PORT"] = str(args.train_monitor_port)
    os.environ["TRAIN_MONITOR_ENABLED"] = "0" if args.disable_train_monitor else "1"
    os.environ["TRAIN_MONITOR_MODE"] = "integrated"
    os.environ["MIKAZUKI_DEV"] = "1" if args.dev else "0"
    if startup.open_browser is not None:
        os.environ["MIKAZUKI_OPEN_BROWSER"] = "1" if startup.open_browser else "0"
    if args.browser:
        os.environ["MIKAZUKI_BROWSER"] = args.browser

    child_processes: list[tuple[str, subprocess.Popen]] = []
    try:
        if not args.disable_tensorboard:
            process = run_tensorboard()
            if process is not None:
                child_processes.append(("TensorBoard", process))

        if not args.disable_train_monitor:
            process = run_train_monitor()
            if process is not None:
                child_processes.append(("train monitor", process))

        import uvicorn
        log.info(f"Starting server at http://{args.host}:{args.port} (readiness not verified)")
        if not args.disable_train_monitor:
            log.info(
                f"Starting train monitor at http://{startup.monitor.host}:{args.train_monitor_port} "
                "(readiness not verified)"
            )
        else:
            log.info("Train monitor disabled by startup settings or port conflict policy")
        uvicorn.run("mikazuki.app:app", host=args.host, port=args.port, log_level="error", reload=args.dev)
    finally:
        stop_child_processes(child_processes)


if __name__ == "__main__":
    # Initialize third-party SDKs/child tools before any download is started.
    # Runtime tasks use explicit policy snapshots; never hot-edit os.environ.
    from mikazuki.networking.policy import initialize_sdk_environment
    initialize_sdk_environment()
    args, _ = parser.parse_known_args()
    launch()


import importlib.util
import os
import site
import sys
import webbrowser
import uuid
from pathlib import Path
from typing import Any, Optional

_VALID_ACCELERATE_MIXED_PRECISION = frozenset({"no", "fp16", "bf16"})

from mikazuki.app.models import APIResponse
from mikazuki.engines.anima_fast.launcher import build_launch_spec
from mikazuki.engines.anima_fast.service_resolver import default_resolver
from mikazuki.engines.musubi.launcher import (
    build_cache_latents_spec,
    build_cache_text_encoder_spec,
    build_train_spec,
)
from mikazuki.log import log
from mikazuki.tasks import TaskStatus, tm
from mikazuki.launch_utils import base_dir_path
from mikazuki.portable_utils import train_env_overrides


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _loads_train_toml(text: str) -> Optional[dict]:
    for loader_name in ("toml", "tomllib"):
        try:
            loader = __import__(loader_name)
        except ModuleNotFoundError:
            continue
        try:
            data = loader.loads(text)
        except (ValueError, TypeError):
            return None
        return data if isinstance(data, dict) else None
    return None


def normalize_mixed_precision(value: Any) -> Optional[str]:
    """Return accelerate-compatible mixed_precision or None when unset/invalid."""
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized or normalized in {"none", "null"}:
        return None
    if normalized in _VALID_ACCELERATE_MIXED_PRECISION:
        return normalized
    return None


def read_mixed_precision_from_train_toml(toml_path: str) -> Optional[str]:
    path = Path(toml_path)
    if not path.is_file():
        return None
    try:
        data = _loads_train_toml(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    if not data:
        return None
    return normalize_mixed_precision(data.get("mixed_precision"))


def _path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (OSError, ValueError):
        return False


def _module_origin_under_user_site(module_name: str) -> bool:
    try:
        user_site = Path(site.getusersitepackages())
    except (AttributeError, TypeError):
        return False

    spec = importlib.util.find_spec(module_name)
    if spec is None:
        return False

    candidates: list[str] = []
    if spec.origin:
        candidates.append(spec.origin)
    if spec.submodule_search_locations:
        candidates.extend(str(location) for location in spec.submodule_search_locations)

    return any(_path_is_relative_to(Path(candidate), user_site) for candidate in candidates)


def _should_disable_user_site() -> bool:
    """Keep portable isolation unless training deps are installed in user site."""
    return not any(_module_origin_under_user_site(name) for name in ("torch", "accelerate"))


def build_accelerate_train_command(
    *,
    trainer_file: str,
    toml_path: str,
    cpu_threads: int = 2,
    gpu_ids: Optional[list] = None,
) -> tuple[list[str], dict[str, str], Optional[str]]:
    """Build accelerate launch argv and env for sd-scripts training."""
    launch_opts = [
        "--num_cpu_threads_per_process",
        str(cpu_threads),
        "--quiet",
    ]
    mixed_precision = read_mixed_precision_from_train_toml(toml_path)
    if mixed_precision:
        launch_opts.extend(["--mixed_precision", mixed_precision])

    launch_entry = Path(__file__).resolve().parent / "accelerate_launch.py"
    args = [
        sys.executable,
        str(launch_entry),
        *launch_opts,
        trainer_file,
        "--config_file",
        toml_path,
    ]

    customize_env = os.environ.copy()
    customize_env.update(train_env_overrides())
    # The training subprocess runs ``python mikazuki/accelerate_launch.py``,
    # whose entry imports ``mikazuki.china_hub``. Launching by script path puts
    # only the script's own directory (``mikazuki/``) on sys.path, not the
    # project root, so portable installs (no editable/site-packages mikazuki)
    # fail with ``ModuleNotFoundError: No module named 'mikazuki'`` (issue #158).
    # Inject the project root onto PYTHONPATH so the package is importable.
    project_root = str(base_dir_path())
    existing_pythonpath = customize_env.get("PYTHONPATH", "")
    path_parts = [p for p in existing_pythonpath.split(os.pathsep) if p]
    if project_root not in path_parts:
        path_parts.insert(0, project_root)
    customize_env["PYTHONPATH"] = os.pathsep.join(path_parts)
    customize_env["ACCELERATE_DISABLE_RICH"] = "1"
    customize_env["PYTHONUNBUFFERED"] = "1"
    customize_env["PYTHONWARNINGS"] = "ignore::FutureWarning,ignore::UserWarning"
    if _should_disable_user_site():
        customize_env["PYTHONNOUSERSITE"] = "1"
    else:
        customize_env.pop("PYTHONNOUSERSITE", None)
    customize_env["NO_COLOR"] = "1"
    customize_env["FORCE_COLOR"] = "0"
    customize_env["TERM"] = "dumb"

    if gpu_ids:
        customize_env["CUDA_VISIBLE_DEVICES"] = ",".join(gpu_ids)
        if len(gpu_ids) > 1:
            multi_gpu_args = ["--multi_gpu", "--num_processes", str(len(gpu_ids))]
            if sys.platform == "win32":
                customize_env["USE_LIBUV"] = "0"
                multi_gpu_args = ["--rdzv_backend", "c10d", *multi_gpu_args]
            args[3:3] = multi_gpu_args

    return args, customize_env, mixed_precision


def build_train_log_urls(task_id: str) -> dict:
    """Construct full http(s) URLs for the train-log viewer + SSE stream.

    Reads host/port from ``MIKAZUKI_HOST`` / ``MIKAZUKI_PORT`` (set in
    ``mikazuki/app/application.py`` at boot). ``0.0.0.0`` is normalized to
    ``127.0.0.1`` so the printed URL is actually clickable from the host
    machine.
    """

    host = os.environ.get("MIKAZUKI_HOST", "127.0.0.1") or "127.0.0.1"
    port = os.environ.get("MIKAZUKI_PORT", "28000") or "28000"
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::", ""} else host
    base = f"http://{display_host}:{port}"
    return {
        "base": base,
        "viewer": f"{base}/train-log?task_id={task_id}",
        "stream": f"{base}/api/train/log/stream/{task_id}",
    }


def _announce_train_log(task_id: str, urls: dict) -> None:
    """Print a prominent, clickable banner pointing at the live log viewer."""

    viewer = urls["viewer"]
    stream = urls["stream"]
    banner = (
        "\n"
        "  Train log viewer (open in browser):\n"
        f"    {viewer}\n"
        f"    SSE stream: {stream}\n"
        f"    task_id   : {task_id}\n"
    )
    log.info(banner)

    if _truthy_env("MIKAZUKI_AUTO_OPEN_TRAIN_LOG"):
        try:
            webbrowser.open(viewer)
        except Exception as exc:  # noqa: BLE001 — best-effort UX nicety
            log.warning(f"Failed to auto-open train log in browser: {exc}")


def run_train(toml_path: str,
              trainer_file: str = "./scripts/train_network.py",
              gpu_ids: Optional[list] = None,
              cpu_threads: Optional[int] = 2,
              metadata: Optional[dict] = None):
    log.info(f"Training started with config file / 训练开始，使用配置文件: {toml_path}")
    cpu_threads = cpu_threads or 2
    args, customize_env, mixed_precision = build_accelerate_train_command(
        trainer_file=trainer_file,
        toml_path=toml_path,
        cpu_threads=cpu_threads,
        gpu_ids=gpu_ids,
    )

    if mixed_precision:
        log.info(
            "Accelerate launch mixed_precision=%s (from TOML); sd-scripts reads the same key "
            "from --config_file. / Accelerate 与训练脚本均使用 mixed_precision=%s",
            mixed_precision,
            mixed_precision,
        )
    else:
        log.warning(
            "No mixed_precision in %s; accelerate launch may default to 'no'. "
            "Set mixed_precision in the GUI (bf16/fp16). / 配置中未设置 mixed_precision，"
            "Accelerate 可能默认为 no",
            toml_path,
        )

    if gpu_ids:
        log.info(f"Using GPU(s) / 使用 GPU: {gpu_ids}")

    task_metadata = {
        "backend": "standard",
        "config_path": str(Path(toml_path).resolve()),
        "trainer_file": trainer_file,
        "cwd": str(Path.cwd()),
        "mixed_precision": mixed_precision,
        "cpu_threads": cpu_threads,
        "gpu_ids": list(gpu_ids or []),
        "command": [str(part) for part in args],
    }
    task_metadata.update(metadata or {})
    task_metadata["job_label"] = "Training"

    task = tm.create_task(args, customize_env, metadata=task_metadata)
    queued = task.status == TaskStatus.QUEUED
    tm.submit(task)

    urls = build_train_log_urls(task.task_id)
    _announce_train_log(task.task_id, urls)

    message = (
        f"Training queued / 训练已加入队列 ID: {task.task_id}"
        if queued else
        f"Training started / 训练开始 ID: {task.task_id}"
    )
    return APIResponse(
        status="success",
        message=message,
        data={
            "task_id": task.task_id,
            "queued": queued,
            "train_log_path": "/train-log",
            "train_log_query": f"task_id={task.task_id}",
            "train_log_stream": f"/api/train/log/stream/{task.task_id}",
            # Full clickable URLs (new in this release).
            "train_log_url": urls["viewer"],
            "train_log_stream_url": urls["stream"],
            "metadata": task_metadata,
            "config_path": task_metadata["config_path"],
            "trainer_file": trainer_file,
        },
    )


def run_musubi_train(toml_path: str,
                     runtime,
                     values: dict,
                     gpu_ids: Optional[list] = None,
                     metadata: Optional[dict] = None):
    """Launch a musubi-tuner Krea 2 run: cache latents -> cache TE outputs -> train."""
    from mikazuki.model_assets import krea2_tokenizer_dir, patch_krea2_tokenizer_path

    log.info(f"musubi-tuner training started with config file / musubi 训练开始，使用配置文件: {toml_path}")
    if gpu_ids:
        log.info(f"Using GPU(s) / 使用 GPU: {gpu_ids}")
        if len(gpu_ids) > 1:
            log.info(
                "Musubi train will use accelerate --multi_gpu; cache stages stay on GPU %s / "
                "训练阶段多卡，缓存阶段仍用 GPU %s",
                gpu_ids[0],
                gpu_ids[0],
            )
    patch_krea2_tokenizer_path(runtime.musubi_root, krea2_tokenizer_dir(runtime.lora_next_root), log=log.info)
    train_task_id = str(uuid.uuid4())
    dataset_toml = Path(str(values["dataset_config"]))
    cache_latents_spec = build_cache_latents_spec(
        runtime, dataset_toml, str(values["vae"]), f"{train_task_id}-cache_latents", gpu_ids
    )
    cache_te_spec = build_cache_text_encoder_spec(
        runtime, dataset_toml, str(values["text_encoder"]), f"{train_task_id}-cache_text_encoder", gpu_ids
    )
    train_spec = build_train_spec(runtime, Path(toml_path), train_task_id, gpu_ids)

    base_metadata = {
        "backend": "musubi",
        "train_type": "krea2-lora",
        "config_path": str(Path(toml_path).resolve()),
        "dataset_config": str(dataset_toml.resolve()),
        "musubi_root": str(runtime.musubi_root),
        "musubi_python": str(runtime.python),
        "train_task_id": train_task_id,
    }
    base_metadata.update(metadata or {})

    stages = [
        ("cache_latents", cache_latents_spec, "缓存图像 latents"),
        ("cache_text_encoder", cache_te_spec, "缓存文本编码器输出"),
        ("train", train_spec, "训练"),
    ]
    tasks = []
    for stage_name, spec, label in stages:
        stage_metadata = dict(base_metadata)
        stage_metadata["stage"] = stage_name
        stage_metadata["stage_label"] = label
        stage_metadata["job_label"] = f"musubi {label}"
        stage_metadata["command"] = [str(part) for part in spec.command]
        task_id = train_task_id if stage_name == "train" else f"{train_task_id}-{stage_name}"
        task = tm.create_task(spec.command, spec.env, metadata=stage_metadata,
                              cwd=str(spec.cwd), task_id=task_id, group=train_task_id)
        tasks.append((label, task))

    queued = any(task.status == TaskStatus.QUEUED for _, task in tasks)
    tm.submit_group([task for _, task in tasks])

    urls = build_train_log_urls(train_task_id)
    _announce_train_log(train_task_id, urls)

    message = (
        f"musubi-tuner training queued / musubi 训练已加入队列 ID: {train_task_id}"
        if queued else
        f"musubi-tuner training started / musubi 训练开始 ID: {train_task_id}"
    )
    return APIResponse(
        status="success",
        message=message,
        data={
            "task_id": train_task_id,
            "queued": queued,
            "cache_latents_task_id": tasks[0][1].task_id,
            "cache_te_task_id": tasks[1][1].task_id,
            "train_log_path": "/train-log",
            "train_log_query": f"task_id={train_task_id}",
            "train_log_stream": f"/api/train/log/stream/{train_task_id}",
            "train_log_url": urls["viewer"],
            "train_log_stream_url": urls["stream"],
            "metadata": base_metadata,
            "config_path": base_metadata["config_path"],
        },
    )


def run_anima_fast_train(toml_path: str,
                         runtime,
                         gpu_ids: Optional[list] = None,
                         metadata: Optional[dict] = None):
    log.info(f"Anima Fast training started with config file / Anima Fast 训练开始，使用配置文件: {toml_path}")
    task_id = str(uuid.uuid4())
    spec = build_launch_spec(runtime, Path(toml_path), task_id, gpu_ids)
    log_file = Path(metadata.get("logging_dir") or runtime.logging_dir) / f"{Path(toml_path).stem}.launch.log" if metadata else runtime.logging_dir / f"{Path(toml_path).stem}.launch.log"
    task_metadata = {
        "backend": "anima-lora-fast",
        "config_path": str(Path(toml_path).resolve()),
        "anima_root": str(runtime.anima_root),
        "anima_python": str(runtime.python),
        "output_dir": str(runtime.output_dir),
        "logging_dir": str(runtime.logging_dir),
        "log_file": str(log_file),
    }
    task_metadata.update(metadata or {})
    task_metadata["job_label"] = "Anima Fast training"

    task = tm.create_task(spec.command, spec.env, metadata=task_metadata, cwd=str(spec.cwd), task_id=task_id)
    queued = task.status == TaskStatus.QUEUED
    tm.submit(task)

    resolver = default_resolver(Path.cwd())
    urls = {
        "viewer": resolver.train_log_viewer_url(task.task_id),
        "stream": resolver.public_base_url().rstrip("/") + resolver.train_log_stream_path(task.task_id),
        "base": resolver.public_base_url(),
    }
    _announce_train_log(task.task_id, urls)

    message = (
        f"Anima Fast training queued / Anima Fast 训练已加入队列 ID: {task.task_id}"
        if queued else
        f"Anima Fast training started / Anima Fast 训练开始 ID: {task.task_id}"
    )
    return APIResponse(
        status="success",
        message=message,
        data={
            "task_id": task.task_id,
            "queued": queued,
            "train_log_path": "/train-log",
            "train_log_query": f"task_id={task.task_id}",
            "train_log_stream": f"/api/train/log/stream/{task.task_id}",
            "train_log_url": urls["viewer"],
            "train_log_stream_url": urls["stream"],
            "metadata": task_metadata,
            "log_file": str(log_file),
        },
    )


def run_ai_toolkit_train(config_yaml: str,
                         runtime,
                         variant: str,
                         gpu_ids: Optional[list] = None,
                         metadata: Optional[dict] = None,
                         te_path: str = ""):
    """Launch an ai-toolkit run: single-stage driver -> `run.py <config.yaml>`."""
    from mikazuki.engines.ai_toolkit.launcher import build_train_spec as build_ai_toolkit_train_spec

    log.info(f"ai-toolkit training started with config file / ai-toolkit 训练开始，使用配置文件: {config_yaml}")
    if gpu_ids:
        log.info(f"Using GPU(s) / 使用 GPU: {gpu_ids}")
    task_id = str(uuid.uuid4())
    spec = build_ai_toolkit_train_spec(runtime, Path(config_yaml), task_id, gpu_ids, te_path=te_path)
    task_metadata = {
        "backend": "ai-toolkit",
        "train_type": f"{variant}-lora",
        "config_path": str(Path(config_yaml).resolve()),
        "toolkit_root": str(runtime.toolkit_root),
        "toolkit_python": str(runtime.python),
        "command": [str(part) for part in spec.command],
    }
    task_metadata.update(metadata or {})
    task_metadata["job_label"] = f"ai-toolkit {variant} training"

    task = tm.create_task(spec.command, spec.env, metadata=task_metadata, cwd=str(spec.cwd), task_id=task_id)
    queued = task.status == TaskStatus.QUEUED
    tm.submit(task)

    urls = build_train_log_urls(task.task_id)
    _announce_train_log(task.task_id, urls)

    message = (
        f"ai-toolkit training queued / ai-toolkit 训练已加入队列 ID: {task.task_id}"
        if queued else
        f"ai-toolkit training started / ai-toolkit 训练开始 ID: {task.task_id}"
    )
    return APIResponse(
        status="success",
        message=message,
        data={
            "task_id": task.task_id,
            "queued": queued,
            "train_log_path": "/train-log",
            "train_log_query": f"task_id={task.task_id}",
            "train_log_stream": f"/api/train/log/stream/{task.task_id}",
            "train_log_url": urls["viewer"],
            "train_log_stream_url": urls["stream"],
            "metadata": task_metadata,
            "config_path": task_metadata["config_path"],
        },
    )

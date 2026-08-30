import asyncio
import hashlib
import json
import os
import re

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from urllib.parse import quote

import mikazuki.process as process
from mikazuki import launch_utils
from mikazuki.engines import registry
from mikazuki.engines.anima_fast import TRAIN_TYPE as ANIMA_FAST_TRAIN_TYPE
from mikazuki.engines.kohya.run import TRAINER_MAPPING as trainer_mapping
from mikazuki.engines.manifest import KIND_BUILTIN
from mikazuki.engines.musubi import TRAIN_TYPE as MUSUBI_TRAIN_TYPE
from mikazuki.engines.runner import RunContext, dispatch_run
from mikazuki.model_assets import (
    check_assets as check_model_assets,
    resolve_train_type as resolve_model_asset_train_type,
    start_download_task as start_model_assets_download_task,
)
from mikazuki.app.train_submit import (
    ANIMA_DEFAULT_SAMPLE_NEGATIVE,
    ANIMA_DEFAULT_SAMPLE_POSITIVE,
    ANIMA_DEFAULT_UNET_LR,
    ANIMA_FINETUNE_TYPE,
    ANIMA_FULL_PRECISION_UNSAFE_OPTIMIZERS,
    ANIMA_LEGACY_UNET_LR,
    ANIMA_TRAIN_TYPES,
    TOKENIZER_CACHE_TRAIN_TYPES,
    _add_training_warning,
    _is_invalid_value,
    _missing_standard_train_field,
    apply_anima_training_defaults,
    apply_sdxl_prediction_type,
    apply_tokenizer_cache_dir,
    get_sample_prompts,
    has_explicit_sample_prompt_source,
    is_preview_enabled,
    sanitize_config,
    should_generate_sample_prompts,
    toml,
)
from mikazuki.app.config import app_config
from mikazuki.app.models import (APIResponse, APIResponseFail,
                                 APIResponseSuccess, TaggerInterrogateRequest,
                                 TaggerPrefetchRequest)
from mikazuki.dataset_editor import router as dataset_editor_router
from mikazuki.log import log
from mikazuki.tagger.interrogator import available_interrogators
from mikazuki.tagger.jobs import run_interrogate_job, run_prefetch_job
from mikazuki.tagger.progress import tagger_progress
from mikazuki.tasks import tm
from mikazuki.train_log_hub import hub as train_log_hub
from mikazuki.utils import task_insights, train_utils
from mikazuki.utils.config_import import validate_config_import
from mikazuki.utils.config_export import normalize_config_for_export
from mikazuki.utils.config_args import normalize_custom_args
from mikazuki.utils.devices import printable_devices
from mikazuki.utils import path_browser as path_browser_utils
from mikazuki.utils.tk_window import (open_directory_selector,
                                      open_file_selector,
                                      tkinter_available)

router = APIRouter()
router.include_router(dataset_editor_router)

avaliable_scripts = [
    "networks/extract_lora_from_models.py",
    "networks/extract_lora_from_dylora.py",
    "networks/merge_lora.py",
    "tools/merge_models.py",
]

avaliable_schemas = []
avaliable_presets = []


async def load_schemas():
    avaliable_schemas.clear()

    schema_dir = os.path.join(os.getcwd(), "mikazuki", "schema")
    schemas = sorted(os.listdir(schema_dir), key=lambda name: (os.path.splitext(name)[0] != "shared", name))

    def lambda_hash(x):
        return hashlib.md5(x.encode()).hexdigest()

    for schema_name in schemas:
        schema_id = os.path.splitext(schema_name)[0]
        with open(os.path.join(schema_dir, schema_name), encoding="utf-8") as f:
            content = f.read()
            avaliable_schemas.append({
                "name": schema_id,
                "schema": content,
                "hash": lambda_hash(content)
            })


async def load_presets():
    avaliable_presets.clear()

    preset_dir = os.path.join(os.getcwd(), "config", "presets")
    presets = os.listdir(preset_dir)

    for preset_name in presets:
        with open(os.path.join(preset_dir, preset_name), encoding="utf-8") as f:
            content = f.read()
            avaliable_presets.append(toml.loads(content))


@router.post("/config/validate-import")
async def validate_import_config(request: Request):
    """Validate imported TOML/JSON config against the current training page."""
    try:
        payload = json.loads(await request.body())
    except json.JSONDecodeError:
        return APIResponseFail(message="请求体必须是 JSON")

    page_train_type = payload.get("page_train_type")
    config = payload.get("config")
    if not page_train_type or not isinstance(page_train_type, str):
        return APIResponseFail(message="缺少 page_train_type")
    if not isinstance(config, dict):
        return APIResponseFail(message="缺少 config 对象")

    result = validate_config_import(page_train_type, config)
    return APIResponseSuccess(data=result)


@router.post("/config/normalize-for-export")
async def normalize_export_config(request: Request):
    """Normalize form config for export/download TOML (Anima uses adapt_anima_config)."""
    try:
        payload = json.loads(await request.body())
    except json.JSONDecodeError:
        return APIResponseFail(message="请求体必须是 JSON")

    page_train_type = payload.get("page_train_type")
    config = payload.get("config")
    if not page_train_type or not isinstance(page_train_type, str):
        return APIResponseFail(message="缺少 page_train_type")
    if not isinstance(config, dict):
        return APIResponseFail(message="缺少 config 对象")

    try:
        cfg, warnings = normalize_config_for_export(
            config,
            page_train_type=page_train_type,
        )
    except Exception as exc:
        log.exception("normalize-for-export failed")
        return APIResponseFail(message=f"预览配置失败: {exc}")

    return APIResponseSuccess(data={"config": cfg, "warnings": warnings})


@router.post("/run")
async def create_toml_file(request: Request):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    autosave_dir = os.path.join(os.getcwd(), "config", "autosave")
    os.makedirs(autosave_dir, exist_ok=True)
    json_data = await request.body()

    config: dict = json.loads(json_data.decode("utf-8"))
    train_utils.fix_config_types(config)
    normalize_custom_args(config)
    train_utils.ensure_enable_preview_flag(config)

    gpu_ids = config.pop("gpu_ids", None)
    model_train_type = config.pop("model_train_type", "sd-lora")

    result = dispatch_run(
        model_train_type,
        config,
        RunContext(
            timestamp=timestamp,
            autosave_dir=autosave_dir,
            gpu_ids=gpu_ids,
            model_train_type=model_train_type,
        ),
    )
    if result is None:
        return APIResponseFail(
            message=f"不支持的训练类型: {model_train_type}",
            data={"model_train_type": model_train_type},
        )
    return result


def _engine_routes_module(engine_id: str):
    pack = registry.get_pack(engine_id)
    if pack is None:
        raise HTTPException(status_code=404, detail=f"Unknown engine: {engine_id}")
    try:
        return pack.import_module("routes")
    except ModuleNotFoundError as exc:
        # Only translate a genuinely missing routes module; a nested import
        # failure inside an existing routes.py must surface as-is.
        if exc.name and exc.name.rsplit(".", 1)[-1] == "routes" and exc.name.startswith(pack.package):
            raise HTTPException(status_code=404, detail=f"Engine {engine_id} exposes no routes")
        raise


async def _engine_payload(request: Request) -> dict:
    return json.loads((await request.body()).decode("utf-8") or "{}")


@router.get("/engines/{engine_id}/status")
async def engine_status(engine_id: str):
    return await _engine_routes_module(engine_id).status()


@router.post("/engines/{engine_id}/preflight")
async def engine_preflight(engine_id: str, request: Request):
    routes = _engine_routes_module(engine_id)
    handler = getattr(routes, "preflight", None)
    if handler is None:
        raise HTTPException(status_code=404, detail=f"Engine {engine_id} has no preflight")
    return await handler(await _engine_payload(request))


@router.post("/engines/{engine_id}/dry-run")
async def engine_dry_run(engine_id: str, request: Request):
    routes = _engine_routes_module(engine_id)
    handler = getattr(routes, "dry_run", None)
    if handler is None:
        raise HTTPException(status_code=404, detail=f"Engine {engine_id} has no dry-run")
    return await handler(await _engine_payload(request))


async def _engine_install_impl(engine_id: str, request: Request, force_install: bool):
    pack = registry.get_pack(engine_id)
    if pack is None:
        raise HTTPException(status_code=404, detail=f"Unknown engine: {engine_id}")
    if pack.manifest.kind == KIND_BUILTIN:
        return APIResponseFail(message=f"{engine_id} 为内置引擎，无需安装。")
    routes = _engine_routes_module(engine_id)
    handler = getattr(routes, "install", None)
    if handler is None:
        return APIResponseFail(message=f"{engine_id} 插件未提供安装接口。")
    return await handler(await _engine_payload(request), force_install=force_install)


@router.post("/engines/{engine_id}/install")
async def engine_install(engine_id: str, request: Request):
    return await _engine_install_impl(engine_id, request, force_install=False)


@router.post("/engines/{engine_id}/repair")
async def engine_repair(engine_id: str, request: Request):
    pack = registry.get_pack(engine_id)
    if pack is None:
        raise HTTPException(status_code=404, detail=f"Unknown engine: {engine_id}")
    if pack.manifest.kind == KIND_BUILTIN:
        return APIResponseFail(message=f"{engine_id} 为内置引擎，无需修复。")
    routes = _engine_routes_module(engine_id)
    handler = getattr(routes, "repair", None)
    if handler is None:
        return await _engine_install_impl(engine_id, request, force_install=True)
    return await handler(await _engine_payload(request))


@router.post("/engines/{engine_id}/uninstall")
async def engine_uninstall(engine_id: str):
    pack = registry.get_pack(engine_id)
    if pack is None:
        raise HTTPException(status_code=404, detail=f"Unknown engine: {engine_id}")
    if pack.manifest.kind == KIND_BUILTIN:
        return APIResponseFail(message=f"{engine_id} 为内置引擎，不可卸载。")
    routes = _engine_routes_module(engine_id)
    handler = getattr(routes, "uninstall", None)
    if handler is None:
        return APIResponseFail(message=f"{engine_id} 插件未提供卸载接口。")
    return await handler()


@router.get("/engines/{engine_id}/install/log/stream/{task_id}")
async def engine_install_log_stream(engine_id: str, task_id: str):
    """Engine install task stdout stream (same payload as train log stream)."""
    _engine_routes_module(engine_id)
    return await train_log_stream(task_id)


@router.get("/engines/{engine_id}/install/progress/stream/{task_id}")
async def engine_install_progress_stream(engine_id: str, task_id: str):
    """Server-Sent Events: structured engine install progress."""
    _engine_routes_module(engine_id)
    if task_id not in tm.tasks:
        raise HTTPException(status_code=404, detail="Unknown task_id")

    async def event_generator():
        idx = 0
        while True:
            await asyncio.sleep(0.08)
            events, total, done = train_log_hub.snapshot_events_from(task_id, idx)
            for event in events:
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
            idx = total
            if done:
                yield "data: " + json.dumps({"type": "done", "done": True}, ensure_ascii=False) + "\n\n"
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/assets/check")
async def model_assets_check(request: Request):
    payload: dict = json.loads((await request.body()).decode("utf-8") or "{}")
    values = payload.get("values") or {}
    if not isinstance(values, dict):
        return APIResponseFail(message="values must be an object")
    train_type = resolve_model_asset_train_type(str(payload.get("train_type") or ""), values)
    return APIResponseSuccess(data={
        "train_type": train_type,
        "items": check_model_assets(train_type, values, Path.cwd()),
    })


@router.post("/assets/download")
async def model_assets_download(request: Request):
    payload: dict = json.loads((await request.body()).decode("utf-8") or "{}")
    values = payload.get("values") or {}
    items = payload.get("items") or []
    source = str(payload.get("source") or "")
    train_type = resolve_model_asset_train_type(str(payload.get("train_type") or ""), values if isinstance(values, dict) else {})
    if not items or not isinstance(items, list):
        return APIResponseFail(message="items must be a non-empty list")
    if source not in {"huggingface", "modelscope"}:
        return APIResponseFail(message="source must be huggingface or modelscope")
    if not train_type:
        return APIResponseFail(message="missing train_type")
    try:
        task_id, data = start_model_assets_download_task(train_type, items, source, Path.cwd())
    except Exception as exc:
        return APIResponseFail(message=f"asset download failed to start: {exc}")
    data["message"] = "asset download task started"
    return APIResponseSuccess(data=data)


@router.post("/run_script")
async def run_script(request: Request, background_tasks: BackgroundTasks):
    paras = await request.body()
    j = json.loads(paras.decode("utf-8"))
    script_name = j["script_name"]
    if script_name not in avaliable_scripts:
        return APIResponseFail(message="Script not found")
    del j["script_name"]
    result = []
    for k, v in j.items():
        result.append(f"--{k}")
        if not isinstance(v, bool):
            value = str(v)
            if " " in value:
                value = f'"{v}"'
            result.append(value)
    script_args = " ".join(result)
    script_path = Path(os.getcwd()) / "scripts" / script_name
    cmd = f"{launch_utils.python_bin} {script_path} {script_args}"
    background_tasks.add_task(launch_utils.run, cmd)
    return APIResponseSuccess()


@router.get("/tagger/status")
async def tagger_status():
    return APIResponseSuccess(data=tagger_progress.get())


@router.get("/tagger/download-status")
async def tagger_download_status():
    snap = tagger_progress.get()
    return APIResponseSuccess(data={
        "phase": snap.get("phase"),
        "model": snap.get("model"),
        "download": snap.get("download"),
        "message": snap.get("message"),
        "error": snap.get("error"),
    })


@router.post("/tagger/cancel")
async def tagger_cancel():
    if not tagger_progress.request_cancel():
        return APIResponseSuccess(message="当前无运行中的任务")
    return APIResponseSuccess(message="正在中止任务…")


@router.post("/tagger/reset")
async def tagger_reset():
    if tagger_progress.is_busy():
        tagger_progress.request_cancel()
    tagger_progress.reset_idle("配置参数后点击启动")
    return APIResponseSuccess(message="已重置打标状态")


@router.post("/tagger/prefetch")
async def tagger_prefetch(req: TaggerPrefetchRequest, background_tasks: BackgroundTasks):
    if req.interrogator_model not in available_interrogators:
        return APIResponseFail(message=f"未知模型: {req.interrogator_model}")
    if tagger_progress.is_busy():
        return APIResponseFail(message="已有打标或下载任务进行中")
    background_tasks.add_task(run_prefetch_job, req)
    return APIResponseSuccess(message="模型下载已开始")


@router.post("/interrogate")
async def run_interrogate(req: TaggerInterrogateRequest, background_tasks: BackgroundTasks):
    if req.interrogator_model not in available_interrogators:
        return APIResponseFail(message=f"未知模型: {req.interrogator_model}")
    if tagger_progress.is_busy():
        return APIResponseFail(message="已有打标或下载任务进行中")
    background_tasks.add_task(run_interrogate_job, req)
    return APIResponseSuccess(message="打标任务已提交")


@router.get("/pick_file")
async def pick_file(picker_type: str):
    """Native tkinter picker (desktop host only). Prefer /api/path_browser on Linux/remote."""
    if not path_browser_utils.gui_picker_available():
        return APIResponseFail(
            message="当前环境无法使用系统文件选择框（无桌面 / 远程访问 / 未安装 tkinter）。"
            "请使用网页路径浏览器，或手动输入服务器上的路径。",
            data={"code": "GUI_PICKER_UNAVAILABLE", "web_picker": True},
        )
    if picker_type == "folder":
        coro = asyncio.to_thread(open_directory_selector, "")
    elif picker_type == "model-file":
        file_types = [("checkpoints", "*.safetensors;*.ckpt;*.pt"), ("all files", "*.*")]
        coro = asyncio.to_thread(open_file_selector, "", "Select file", file_types)
    else:
        return APIResponseFail(message=f"不支持的 picker_type: {picker_type}")

    result = await coro
    if result == "":
        return APIResponseFail(message="用户取消选择", data={"code": "CANCELLED", "web_picker": True})

    return APIResponseSuccess(data={
        "path": result
    })


@router.get("/path_browser/capability")
async def path_browser_capability():
    return APIResponseSuccess(data={
        "web_picker": True,
        "gui_picker": path_browser_utils.gui_picker_available(),
        "tkinter": tkinter_available(),
    })


@router.get("/path_browser/list")
async def path_browser_list(
    path: str = "",
    mode: str = "folder",
    name_filter: str = "",
):
    """List a server directory for the in-browser path picker (#244)."""
    try:
        data = await asyncio.to_thread(
            path_browser_utils.list_directory,
            path or None,
            mode=mode,
            name_filter=name_filter or None,
        )
    except PermissionError as exc:
        return APIResponseFail(message=str(exc), data={"code": "DENIED"})
    except FileNotFoundError as exc:
        return APIResponseFail(message=str(exc), data={"code": "NOT_FOUND"})
    except (NotADirectoryError, ValueError, OSError) as exc:
        return APIResponseFail(message=str(exc), data={"code": "BAD_PATH"})
    return APIResponseSuccess(data=data)


@router.get("/path_browser/image")
async def path_browser_image(path: str, thumb: bool = True):
    """Serve a selected local image, using a thumbnail by default."""
    try:
        image_path = await asyncio.to_thread(path_browser_utils.resolve_image_path, path)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    headers = {"Cache-Control": "private, max-age=60"}
    if thumb:
        data = await asyncio.to_thread(task_insights.preview_thumbnail, image_path)
        if data is not None:
            return Response(content=data, media_type="image/jpeg", headers=headers)
    return FileResponse(str(image_path), headers=headers)


@router.get("/get_files")
async def get_files(pick_type) -> APIResponse:
    pick_preset = {
        "model-file": {
            "type": "file",
            "path": "./sd-models",
            "filter": "(.safetensors|.ckpt|.pt)"
        },
        "model-saved-file": {
            "type": "file",
            "path": "./output",
            "filter": "(.safetensors|.ckpt|.pt)"
        },
        "train-dir": {
            "type": "folder",
            "path": "./train",
            "filter": None
        },
    }

    folder_blacklist = [".ipynb_checkpoints", ".DS_Store"]

    def list_path_or_files(preset_info):
        path = Path(preset_info["path"])
        file_type = preset_info["type"]
        regex_filter = preset_info["filter"]
        result_list = []

        if file_type == "file":
            if regex_filter:
                pattern = re.compile(regex_filter)
                files = [f for f in path.glob("**/*") if f.is_file() and pattern.search(f.name)]
            else:
                files = [f for f in path.glob("**/*") if f.is_file()]
            for file in files:
                stat = file.stat()
                result_list.append({
                    "path": str(file.resolve().absolute()).replace("\\", "/"),
                    "name": file.name,
                    "size": f"{round(stat.st_size / (1024**3),2)} GB",
                    "size_bytes": stat.st_size,
                    "mtime": int(stat.st_mtime),
                })
        elif file_type == "folder":
            folders = [f for f in path.iterdir() if f.is_dir()]
            for folder in folders:
                if folder.name in folder_blacklist:
                    continue
                result_list.append({
                    "path": str(folder.resolve().absolute()).replace("\\", "/"),
                    "name": folder.name,
                    "size": 0
                })

        return result_list

    if pick_type not in pick_preset:
        return APIResponseFail(message="Invalid request")

    dirs = list_path_or_files(pick_preset[pick_type])
    return APIResponseSuccess(data={
        "files": dirs
    })


@router.get("/tasks", response_model_exclude_none=True)
async def get_tasks() -> APIResponse:
    tasks = tm.dump()
    for item in tasks:
        # Older tasks never persisted train_type; derive it so the UI
        # train-type filter works for history as well (#291 review).
        metadata = item.get("metadata") or {}
        if not metadata.get("train_type"):
            task = tm.tasks.get(item["id"])
            derived = _task_train_type(task) if task is not None else None
            if derived:
                metadata["train_type"] = derived
    return APIResponseSuccess(data={
        "tasks": tasks
    })


@router.get("/tasks/terminate/{task_id}", response_model_exclude_none=True)
async def terminate_task(task_id: str):
    tm.terminate_task(task_id)
    return APIResponseSuccess()


@router.get("/tasks/resume/{task_id}", response_model_exclude_none=True)
async def resume_task(task_id: str):
    """Release a restored queued task that is waiting for manual confirmation."""
    if tm.resume_task(task_id):
        return APIResponseSuccess(data={"resumed": True})
    return APIResponseFail(message="Task is not a held queued task / 任务不在待确认队列中")


@router.get("/tasks/retry/{task_id}", response_model_exclude_none=True)
async def retry_task(task_id: str):
    """Re-queue a finished/failed/terminated training task (stage groups are
    rebuilt as a whole)."""
    new_tasks = tm.retry_task(task_id)
    if not new_tasks:
        return APIResponseFail(message="Task cannot be retried / 任务无法重跑（仅支持已结束的训练任务）")
    return APIResponseSuccess(data={
        "task_id": new_tasks[-1].task_id,
        "task_ids": [t.task_id for t in new_tasks],
        "queued": any(t.status.name == "QUEUED" for t in new_tasks),
    })


def _task_train_type(task) -> Optional[str]:
    """Recover the page-level train type for a task so its config can be
    re-imported into the matching training page."""
    backend = str(task.metadata.get("backend") or "standard")
    if backend == "anima-lora-fast":
        return ANIMA_FAST_TRAIN_TYPE
    if backend == "ai-toolkit":
        train_type = task.metadata.get("train_type")
        return str(train_type) if train_type else None
    if backend == "musubi":
        train_type = task.metadata.get("train_type")
        return str(train_type) if train_type else MUSUBI_TRAIN_TYPE
    trainer_file = str(task.metadata.get("trainer_file") or "")
    for train_type, path in trainer_mapping.items():
        if path == trainer_file:
            return train_type
    return None


@router.get("/tasks/{task_id}/config", response_model_exclude_none=True)
async def task_config(task_id: str) -> APIResponse:
    """Return the task's autosave TOML as JSON for re-import / export."""
    task = tm.tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Unknown task_id")
    config_path = task.metadata.get("config_path")
    if not config_path:
        return APIResponseFail(message="Task has no config file / 该任务没有关联的配置文件")
    path = Path(str(config_path))
    if not path.is_file():
        return APIResponseFail(message="Config file no longer exists / 配置文件已不存在（autosave 可能已被清理）")
    try:
        config = toml.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return APIResponseFail(message=f"配置解析失败: {exc}")
    train_type = _task_train_type(task)
    if train_type and not config.get("model_train_type"):
        config["model_train_type"] = train_type
    return APIResponseSuccess(data={
        "config": config,
        "config_path": str(path),
        "backend": str(task.metadata.get("backend") or "standard"),
        "train_type": train_type,
        "output_name": task.metadata.get("output_name"),
    })


@router.post("/tasks/{task_id}/move-to-front", response_model_exclude_none=True)
async def move_task_to_front(task_id: str):
    """Move a queued task (held included) right after the running task.
    Stage groups jump as a whole, preserving stage order."""
    if tm.move_to_front(task_id):
        return APIResponseSuccess(data={"moved": True, "queue_position": tm.queue_position(task_id)})
    return APIResponseFail(message="Task is not in the queue / 任务不在队列中")


@router.delete("/tasks/{task_id}", response_model_exclude_none=True)
async def delete_task(task_id: str):
    """Delete a terminal (finished/failed/terminated) task from the list."""
    if tm.delete_task(task_id):
        return APIResponseSuccess(data={"deleted": True})
    return APIResponseFail(message="Task not found or still active / 任务不存在或仍在进行中")


@router.post("/tasks/purge", response_model_exclude_none=True)
async def purge_tasks(request: Request):
    """Bulk-delete terminal tasks, keeping the most recent ``keep_last``."""
    try:
        payload = json.loads(await request.body() or b"{}")
    except json.JSONDecodeError:
        return APIResponseFail(message="请求体必须是 JSON")
    keep_last = payload.get("keep_last", 0)
    if isinstance(keep_last, bool) or not isinstance(keep_last, int) or keep_last < 0:
        return APIResponseFail(message="keep_last 必须是非负整数")
    removed = tm.purge_tasks(keep_last=keep_last)
    return APIResponseSuccess(data={"removed": removed})


@router.get("/tasks/{task_id}/previews", response_model_exclude_none=True)
async def task_previews(task_id: str) -> APIResponse:
    task = tm.tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Unknown task_id")
    images = [
        {
            **item,
            "url": f"/api/tasks/{quote(task_id)}/previews/{quote(item['name'])}",
            "thumb_url": f"/api/tasks/{quote(task_id)}/previews/{quote(item['name'])}?thumb=1",
        }
        for item in task_insights.list_preview_images(task.metadata)
    ]
    config = task_insights.resolve_task_config(task.metadata)
    preview_enabled = bool(config.get("sample_prompts")) if config else None
    return APIResponseSuccess(data={"images": images, "preview_enabled": preview_enabled})


@router.get("/tasks/{task_id}/previews/{filename}")
async def task_preview_image(task_id: str, filename: str, thumb: bool = False):
    task = tm.tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Unknown task_id")
    path = task_insights.resolve_preview_image(task.metadata, filename)
    if path is None:
        raise HTTPException(status_code=404, detail="Unknown preview image")
    headers = {"Cache-Control": "private, max-age=30"}
    if thumb:
        data = task_insights.preview_thumbnail(path)
        if data is not None:
            return Response(content=data, media_type="image/jpeg", headers=headers)
    return FileResponse(path, headers=headers)


def _pack_progress_reader(backend: str):
    """Optional pack hook: a pack may ship ``progress.py`` exposing
    ``read_progress(lines, metadata)``; absent packs fall back to the
    kohya-style stdout parser."""
    if not backend or backend == "standard":
        return None
    pack = registry.get_pack(backend)
    if pack is None:
        return None
    try:
        module = pack.import_module("progress")
    except ImportError:
        return None
    return getattr(module, "read_progress", None)


@router.get("/tasks/{task_id}/metrics", response_model_exclude_none=True)
async def task_metrics(task_id: str) -> APIResponse:
    task = tm.tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Unknown task_id")
    lines = train_log_hub.tail(task_id, 300)
    reader = _pack_progress_reader(str(task.metadata.get("backend") or ""))
    progress = reader(lines, task.metadata) if reader else task_insights.read_progress(lines)
    return APIResponseSuccess(data={
        "tags": task_insights.read_loss_scalars(task.metadata),
        "progress": progress,
    })


@router.get("/graphic_cards")
async def list_avaliable_cards() -> APIResponse:
    if not printable_devices:
        return APIResponse(status="pending")

    return APIResponseSuccess(data={
        "cards": printable_devices
    })


@router.get("/schemas/hashes")
async def list_schema_hashes() -> APIResponse:
    if os.environ.get("MIKAZUKI_SCHEMA_HOT_RELOAD", "0") == "1":
        log.info("Hot reloading schemas")
        await load_schemas()

    return APIResponseSuccess(data={
        "schemas": [
            {
                "name": schema["name"],
                "hash": schema["hash"]
            }
            for schema in avaliable_schemas
        ]
    })


@router.get("/schemas/all")
async def get_all_schemas() -> APIResponse:
    return APIResponseSuccess(data={
        "schemas": avaliable_schemas
    })


@router.get("/presets")
async def get_presets() -> APIResponse:
    if os.environ.get("MIKAZUKI_SCHEMA_HOT_RELOAD", "0") == "1":
        log.info("Hot reloading presets")
        await load_presets()

    return APIResponseSuccess(data={
        "presets": avaliable_presets
    })


@router.get("/config/saved_params")
async def get_saved_params() -> APIResponse:
    saved_params = app_config["saved_params"]
    return APIResponseSuccess(data=saved_params)


@router.get("/train/log/stream/{task_id}")
async def train_log_stream(task_id: str):
    """
    Server-Sent Events: live training stdout (one JSON object per event: {text:...} or {done:true}).
    Open in browser: /train-log?task_id=<uuid>
    """
    if task_id not in tm.tasks:
        raise HTTPException(
            status_code=404,
            detail="Unknown task_id. It is only valid for jobs started in this server session (or the run has not been created).",
        )

    async def event_generator():
        idx = 0
        while True:
            await asyncio.sleep(0.08)
            chunk, total, done = train_log_hub.snapshot_from(task_id, idx)
            for line in chunk:
                yield "data: " + json.dumps({"text": line}, ensure_ascii=False) + "\n\n"
            idx = total
            if done:
                yield "data: " + json.dumps({"done": True}, ensure_ascii=False) + "\n\n"
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/train/log/tail/{task_id}")
async def train_log_tail(task_id: str, limit: int = 240):
    """Recent training stdout lines for the lightweight monitor page."""
    if task_id not in tm.tasks:
        raise HTTPException(status_code=404, detail="Unknown task_id")

    limit = max(1, min(limit, 2000))
    lines, total, done = train_log_hub.snapshot_from(task_id, 0)
    return APIResponseSuccess(data={
        "task_id": task_id,
        "lines": lines[-limit:],
        "total": total,
        "done": done,
    })


@router.get("/train/tasks")
async def list_train_tasks():
    """Running / known training tasks (for tying UI to task_id)."""
    return APIResponseSuccess(data={"tasks": tm.dump()})


@router.get("/check_update")
async def check_update():
    """Non-blocking update check against GitHub Releases."""
    from mikazuki.update_check import get_cached_result, check_update as do_check
    result = get_cached_result()
    if result is None:
        result = await asyncio.to_thread(do_check)
    return APIResponseSuccess(data=result)


@router.get("/version")
async def get_version():
    from mikazuki.update_check import local_version
    return APIResponseSuccess(data={"version": local_version()})

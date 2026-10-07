"""Narrow API for server-owned user configuration; credential reads are masked."""

import json
import re
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from mikazuki.user_data import MAX_BYTES, RevisionConflict, UserDataError, UserDataStore

router = APIRouter(prefix="/user-data")
store = UserDataStore()


def _response(data=None, message=None, status=200):
    return JSONResponse({"status": "success" if status == 200 else "fail",
                         "data": data, "message": message},
                        status_code=status, headers={"Cache-Control": "no-store"})


async def _call(operation, *args, data_key=None):
    try:
        data = await run_in_threadpool(operation, *args)
        return _response({data_key: data} if data_key else data)
    except RevisionConflict as exc:
        return _response(message=str(exc), status=409)
    except UserDataError as exc:
        return _response(message=str(exc), status=422)
    except OSError:
        return _response(message="User data storage is unavailable; nothing was saved", status=503)


async def _body(request, allowed):
    if request.headers.get("sec-fetch-site") == "cross-site":
        return _response(message="Cross-site configuration writes are not allowed", status=403)
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        return _response(message="application/json is required", status=415)
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_BYTES:
            return _response(message="Request is too large", status=413)
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        return _response(message="Invalid JSON", status=422)
    if not isinstance(data, dict) or set(data) != set(allowed):
        return _response(message="Invalid request fields", status=422)
    if type(data.get("revision")) is not int or data["revision"] < 0:
        return _response(message="Invalid revision", status=422)
    return data


@router.get("/settings")
async def read_settings():
    return await _call(store.read_settings)


@router.patch("/settings")
async def patch_settings(request: Request):
    data = await _body(request, {"revision", "patch"})
    if isinstance(data, JSONResponse):
        return data
    return await _call(store.patch_settings, data["patch"], data["revision"])


@router.get("/auth")
async def read_auth():
    return await _call(store.credential_metadata)


@router.put("/auth/{provider}")
async def write_auth(provider: str, request: Request):
    data = await _body(request, {"revision", "secret"})
    if isinstance(data, JSONResponse):
        return data
    return await _call(store.set_credential, provider, data["secret"], data["revision"])


def _preset_payload(data):
    if not isinstance(data, dict):
        raise UserDataError("Preset must be an object")
    preset_id = data.get("id") or f"preset-{uuid.uuid4().hex[:12]}"
    if not isinstance(preset_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", preset_id):
        raise UserDataError("Invalid preset id")
    return preset_id, data


@router.get("/presets")
async def list_presets(train_type: str | None = None):
    return await _call(store.list_presets, train_type, data_key="presets")


@router.get("/presets/{preset_id}")
async def read_preset(preset_id: str):
    return await _call(store.get_preset, preset_id)


@router.post("/presets")
async def create_preset(request: Request):
    try:
        data = json.loads(await request.body() or b"{}")
        if not isinstance(data, dict) or set(data) - {"id", "name", "description", "train_type", "config"}:
            raise UserDataError("Invalid preset fields")
        if len(json.dumps(data).encode("utf-8")) > MAX_BYTES:
            raise UserDataError("Request is too large")
    except (ValueError, UnicodeError) as exc:
        return _response(message="Invalid JSON", status=422)
    try:
        preset_id, payload = _preset_payload(data)
        return _response(await run_in_threadpool(store.save_preset, preset_id, payload, False))
    except RevisionConflict as exc:
        return _response(message=str(exc), status=409)
    except UserDataError as exc:
        return _response(message=str(exc), status=422)


@router.patch("/presets/{preset_id}")
async def update_preset(preset_id: str, request: Request):
    try:
        data = json.loads(await request.body() or b"{}")
        if not isinstance(data, dict) or not data or set(data) - {"name", "description", "train_type", "config"}:
            raise UserDataError("Invalid preset fields")
    except (ValueError, UnicodeError):
        return _response(message="Invalid JSON", status=422)
    try:
        current = await run_in_threadpool(store.get_preset, preset_id)
        current.update(data)
        return _response(await run_in_threadpool(store.save_preset, preset_id, current, True))
    except UserDataError as exc:
        return _response(message=str(exc), status=422)


@router.delete("/presets/{preset_id}")
async def remove_preset(preset_id: str):
    try:
        await run_in_threadpool(store.delete_preset, preset_id)
        return _response({"removed": True})
    except UserDataError as exc:
        return _response(message=str(exc), status=422)


@router.get("/task-archives")
async def list_task_archives(train_type: str | None = None):
    return await _call(store.list_task_archives, train_type, data_key="archives")


@router.get("/task-archives/{archive_id}")
async def read_task_archive(archive_id: str):
    return await _call(store.get_task_archive, archive_id)

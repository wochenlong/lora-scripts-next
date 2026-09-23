from fastapi import APIRouter, HTTPException, Request
from pathlib import Path
from pydantic import BaseModel
from starlette.datastructures import UploadFile as StarletteUploadFile

from mikazuki.app.models import APIResponseSuccess
from mikazuki.datasets.copy import copy_dataset
from mikazuki.datasets.export import file_download_response, stream_dataset_zip
from mikazuki.datasets.in_use import in_use_map, in_use_tasks
from mikazuki.datasets.listing import list_datasets
from mikazuki.datasets.locks import dataset_operation
from mikazuki.datasets.rename import rename_dataset
from mikazuki.datasets.root import (
    DEFAULT_DATASETS_ROOT,
    get_datasets_root,
    normalize_path,
    set_datasets_root,
)
from mikazuki.datasets.sandbox import resolve_dataset_dir
from mikazuki.datasets.stats import cached_overview, get_overview, invalidate_overview
from mikazuki.datasets.trash import (
    empty_trash,
    empty_trash_any,
    list_all_trash,
    list_trash,
    restore_batch,
    restore_batch_by_id,
    soft_delete,
    soft_delete_dataset,
)
from mikazuki.datasets.upload import (
    MAX_BATCH_BYTES,
    cleanup_staging,
    ensure_capacity,
    ensure_staging_headroom,
    move_staged,
    new_staging_dir,
    relative_of,
    resolve_upload_target,
    sanitize_relative_path,
    stage_upload,
    validate_readable,
)

router = APIRouter()


class RootUpdateRequest(BaseModel):
    path: str


class DatasetCreateRequest(BaseModel):
    name: str


class DatasetCopyRequest(BaseModel):
    new_name: str


class DatasetRenameRequest(BaseModel):
    new_name: str


class UploadCheckRequest(BaseModel):
    paths: list[str]


class DeleteFilesRequest(BaseModel):
    paths: list[str]


class TrashRestoreRequest(BaseModel):
    id: str


class TrashEmptyRequest(BaseModel):
    id: str | None = None
    confirm: bool = False


def root_payload() -> dict:
    root = get_datasets_root()
    return {
        "root": normalize_path(root),
        "default": DEFAULT_DATASETS_ROOT,
        "exists": root.is_dir(),
    }


@router.get("/datasets/root")
async def get_root():
    return APIResponseSuccess(data=root_payload())


@router.put("/datasets/root")
async def update_root(req: RootUpdateRequest):
    try:
        set_datasets_root(req.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"cannot create datasets root: {exc}") from exc
    return APIResponseSuccess(data=root_payload())


@router.get("/datasets")
async def list_all():
    root = get_datasets_root()
    usage = in_use_map(root)
    datasets = []
    for item in list_datasets(root):
        datasets.append({**item, "overview": cached_overview(root / item["name"]), "in_use": usage.get(item["name"], [])})
    return APIResponseSuccess(
        data={
            "root": normalize_path(root),
            "exists": root.is_dir(),
            "datasets": datasets,
        }
    )


@router.post("/datasets/{name}/copy")
async def copy(name: str, req: DatasetCopyRequest):
    root = get_datasets_root()
    target = copy_dataset(root, name, req.new_name)
    invalidate_overview(target)
    return APIResponseSuccess(data={"name": target.name, "path": normalize_path(target)})


@router.post("/datasets/{name}/rename")
async def rename(name: str, req: DatasetRenameRequest):
    root = get_datasets_root()
    mutable_dataset_dir(name)
    target = rename_dataset(root, name, req.new_name)
    invalidate_overview(resolve_dataset_dir(root, name))
    invalidate_overview(target)
    return APIResponseSuccess(data={"name": target.name, "path": normalize_path(target)})


@router.get("/datasets/{name}/overview")
async def overview(name: str):
    dataset_dir = resolve_dataset_dir(get_datasets_root(), name)
    if not dataset_dir.is_dir():
        raise HTTPException(status_code=404, detail="dataset not found")
    return APIResponseSuccess(data={"name": dataset_dir.name, "overview": get_overview(dataset_dir), "in_use": in_use_tasks(get_datasets_root(), dataset_dir.name)})


@router.get("/datasets/{name}/file")
async def download_file(name: str, path: str):
    dataset_dir = resolve_dataset_dir(get_datasets_root(), name)
    if not dataset_dir.is_dir():
        raise HTTPException(status_code=404, detail="dataset not found")
    return file_download_response(dataset_dir, path)


@router.get("/datasets/{name}/download")
async def download_dataset(name: str):
    dataset_dir = resolve_dataset_dir(get_datasets_root(), name)
    if not dataset_dir.is_dir():
        raise HTTPException(status_code=404, detail="dataset not found")
    return stream_dataset_zip(dataset_dir)


@router.post("/datasets")
async def create(req: DatasetCreateRequest):
    root = get_datasets_root()
    dataset_dir = resolve_dataset_dir(root, req.name)
    with dataset_operation(dataset_dir.name):
        if dataset_dir.exists():
            raise HTTPException(status_code=409, detail="dataset already exists")
        try:
            dataset_dir.mkdir(parents=True)
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"cannot create dataset: {exc}") from exc
    invalidate_overview(dataset_dir)
    return APIResponseSuccess(data={"name": dataset_dir.name, "path": normalize_path(dataset_dir)})


def existing_dataset_dir(name: str) -> Path:
    dataset_dir = resolve_dataset_dir(get_datasets_root(), name)
    if not dataset_dir.is_dir():
        raise HTTPException(status_code=404, detail="dataset not found")
    return dataset_dir


def mutable_dataset_dir(name: str) -> Path:
    dataset_dir = existing_dataset_dir(name)
    refs = in_use_tasks(get_datasets_root(), dataset_dir.name)
    if refs:
        labels = ", ".join(ref["job_label"] or ref["task_id"] for ref in refs)
        raise HTTPException(status_code=409, detail=f"dataset is in use by queued or running tasks: {labels}")
    return dataset_dir


@router.get("/datasets/{name}/trash")
async def trash_list(name: str):
    dataset_dir = existing_dataset_dir(name)
    return APIResponseSuccess(data={"dataset": dataset_dir.name, "batches": list_trash(get_datasets_root(), dataset_dir.name)})


@router.post("/datasets/{name}/trash/restore")
async def trash_restore(name: str, req: TrashRestoreRequest):
    dataset_dir = mutable_dataset_dir(name)
    with dataset_operation(dataset_dir.name):
        result = restore_batch(get_datasets_root(), dataset_dir, req.id)
    if result["restored"]:
        invalidate_overview(dataset_dir)
    return APIResponseSuccess(data=result)


@router.post("/datasets/{name}/trash/empty")
async def trash_empty(name: str, req: TrashEmptyRequest):
    dataset_dir = mutable_dataset_dir(name)
    if not req.confirm:
        raise HTTPException(status_code=400, detail="emptying the trash requires confirm=true")
    with dataset_operation(dataset_dir.name):
        result = empty_trash(get_datasets_root(), dataset_dir.name, req.id)
    return APIResponseSuccess(data=result)


@router.delete("/datasets/{name}/files")
async def delete_files(name: str, req: DeleteFilesRequest):
    dataset_dir = mutable_dataset_dir(name)
    if not req.paths:
        raise HTTPException(status_code=400, detail="no paths given")
    with dataset_operation(dataset_dir.name):
        result = soft_delete(get_datasets_root(), dataset_dir, req.paths)
    if result["deleted"]:
        invalidate_overview(dataset_dir)
    return APIResponseSuccess(data=result)


@router.delete("/datasets/{name}")
async def delete_dataset(name: str):
    dataset_dir = mutable_dataset_dir(name)
    with dataset_operation(dataset_dir.name):
        result = soft_delete_dataset(get_datasets_root(), dataset_dir)
    invalidate_overview(dataset_dir)
    return APIResponseSuccess(data=result)


@router.get("/datasets-trash")
async def trash_list_all():
    return APIResponseSuccess(data={"batches": list_all_trash(get_datasets_root())})


@router.post("/datasets-trash/restore")
async def trash_restore_any(req: TrashRestoreRequest):
    root = get_datasets_root()
    result = restore_batch_by_id(root, req.id)
    if result["restored"]:
        invalidate_overview(resolve_dataset_dir(root, result["dataset"]))
    return APIResponseSuccess(data=result)


@router.post("/datasets-trash/empty")
async def trash_empty_any(req: TrashEmptyRequest):
    if not req.confirm:
        raise HTTPException(status_code=400, detail="emptying the trash requires confirm=true")
    return APIResponseSuccess(data=empty_trash_any(get_datasets_root(), req.id))


@router.post("/datasets/{name}/upload/check")
async def upload_check(name: str, req: UploadCheckRequest):
    dataset_dir = resolve_dataset_dir(get_datasets_root(), name)
    if not dataset_dir.is_dir():
        raise HTTPException(status_code=404, detail="dataset not found")
    conflicts: list[str] = []
    invalid: list[dict] = []
    ok = 0
    for raw in req.paths:
        try:
            rel = sanitize_relative_path(raw)
            target = resolve_upload_target(dataset_dir, rel)
        except ValueError as exc:
            invalid.append({"path": raw, "reason": str(exc)})
            continue
        if target.exists():
            conflicts.append(rel)
        else:
            ok += 1
    return APIResponseSuccess(data={"conflicts": conflicts, "invalid": invalid, "ok": ok})


@router.post("/datasets/{name}/upload")
async def upload(name: str, request: Request):
    root = get_datasets_root()
    dataset_dir = mutable_dataset_dir(name)

    form = await request.form()
    conflict = str(form.get("conflict", "skip"))
    if conflict not in ("skip", "overwrite"):
        raise HTTPException(status_code=400, detail="conflict must be 'skip' or 'overwrite'")
    uploads = [item for item in form.getlist("files") if isinstance(item, StarletteUploadFile)]
    if not uploads:
        raise HTTPException(status_code=400, detail="no files uploaded")

    succeeded: list[str] = []
    skipped: list[str] = []
    failed: list[dict] = []
    staged_ok: list[tuple[str, Path, int]] = []
    seen: set[str] = set()
    total = 0
    batch_full = False
    staging = new_staging_dir(root)

    try:
        for item in uploads:
            raw_name = item.filename or ""
            try:
                rel = sanitize_relative_path(raw_name)
                resolve_upload_target(dataset_dir, rel)
            except ValueError as exc:
                failed.append({"path": raw_name, "reason": str(exc)})
                continue
            if rel in seen:
                failed.append({"path": rel, "reason": "duplicate path in batch"})
                continue
            seen.add(rel)
            if batch_full:
                failed.append({"path": rel, "reason": "batch size limit exceeded"})
                continue
            try:
                staged, written = await stage_upload(item, staging, rel)
                ensure_staging_headroom(staging)
            except ValueError as exc:
                failed.append({"path": rel, "reason": str(exc)})
                continue
            total += written
            if total > MAX_BATCH_BYTES:
                staged.unlink(missing_ok=True)
                failed.append({"path": rel, "reason": "batch size limit exceeded"})
                batch_full = True
                continue
            try:
                validate_readable(staged)
            except ValueError as exc:
                staged.unlink(missing_ok=True)
                failed.append({"path": rel, "reason": str(exc)})
                continue
            staged_ok.append((rel, staged, written))

        moves: list[tuple[Path, Path]] = []
        for rel, staged, _written in staged_ok:
            target = resolve_upload_target(dataset_dir, rel)
            moves.append((staged, target))

        with dataset_operation(dataset_dir.name):
            if not dataset_dir.is_dir():
                raise HTTPException(status_code=409, detail="dataset was removed during upload")
            ensure_capacity(dataset_dir, moves)
            overwrite = conflict == "overwrite"
            for staged, target in moves:
                if move_staged(staged, target, overwrite):
                    succeeded.append(relative_of(dataset_dir, target))
                else:
                    skipped.append(relative_of(dataset_dir, target))
    finally:
        cleanup_staging(staging)

    if succeeded:
        invalidate_overview(dataset_dir)
    return APIResponseSuccess(
        data={
            "dataset": dataset_dir.name,
            "succeeded": succeeded,
            "skipped": skipped,
            "failed": failed,
        }
    )

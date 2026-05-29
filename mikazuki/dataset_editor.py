from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

import base64
import copy
import mimetypes
import time

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, Field

from mikazuki.app.models import APIResponseSuccess
from mikazuki.tagger.interrogator import available_interrogators
from mikazuki.tagger.interrogators.base import Interrogator
from mikazuki.tagger.model_fetch import ensure_interrogator_assets, use_download_endpoint


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

router = APIRouter()
_UNDO_STACKS: dict[str, list["EditTransaction"]] = {}
_REDO_STACKS: dict[str, list["EditTransaction"]] = {}


@dataclass
class CaptionSnapshot:
    image: str
    caption: str
    caption_exists: bool


@dataclass
class EditTransaction:
    label: str
    before: list[CaptionSnapshot]
    after: list[CaptionSnapshot]


class DatasetScanRequest(BaseModel):
    path: str


class CaptionWriteRequest(BaseModel):
    root: str
    image: str
    caption: str = ""


class TagReplacement(BaseModel):
    source: str = Field(alias="from")
    target: str = Field(alias="to")


class BatchEditRequest(BaseModel):
    root: str
    images: list[str]
    append: list[str] = []
    remove: list[str] = []
    replace: list[TagReplacement] = []
    sort: bool = False
    clean: bool = False
    underscore_to_space: bool = False
    strip_escape_chars: bool = False


class DatasetTagRequest(BaseModel):
    root: str
    images: list[str]
    provider: str = Field(default="local", pattern="^(local|api)$")
    caption_type: str = Field(default="tags", pattern="^(tags|caption)$")
    on_conflict: str = Field(default="copy", pattern="^(ignore|copy|append|prepend)$")
    interrogator_model: str = "wd14-convnextv2-v2"
    threshold: float = Field(default=0.35, ge=0, le=1)
    character_threshold: float = Field(default=0.6, ge=0, le=1)
    add_rating_tag: bool = False
    add_model_tag: bool = False
    additional_tags: str = ""
    exclude_tags: str = ""
    replace_underscore: bool = True
    escape_tag: bool = True
    download_endpoint: str = ""
    api_endpoint: str = "https://api.openai.com/v1"
    api_key: str = ""
    api_model: str = ""
    api_prompt: str = (
        "Describe this image for image model training. Return a concise caption only, "
        "without markdown or explanations."
    )


class UndoRequest(BaseModel):
    root: str


def normalize_path(path: str) -> str:
    return str(Path(path).resolve()).replace("\\", "/")


def normalize_relative_path(path: str | Path) -> str:
    return str(path).replace("\\", "/")


def parse_tags(caption: str) -> list[str]:
    tags = []
    seen = set()
    for raw in caption.split(","):
        tag = raw.strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags


def normalize_caption_for_cleanup(caption: str, underscore_to_space: bool = False, strip_escape_chars: bool = False) -> list[str]:
    normalized = (
        caption.replace("，", ",")
        .replace("；", ",")
        .replace(";", ",")
        .replace("\r", ",")
        .replace("\n", ",")
    )
    tags = []
    seen = set()
    for tag in parse_tags(normalized):
        if strip_escape_chars:
            tag = tag.replace("\\(", "(").replace("\\)", ")").replace("\\[", "[").replace("\\]", "]")
        if underscore_to_space:
            tag = tag.replace("_", " ")
        tag = " ".join(tag.split())
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags


def format_tags(tags: list[str]) -> str:
    return ", ".join(tags)


def merge_caption(existing: str, generated: str, on_conflict: str) -> str | None:
    if existing and on_conflict == "ignore":
        return None
    if not existing or on_conflict == "copy":
        return generated.strip()
    if on_conflict == "prepend":
        return format_tags(parse_tags(f"{generated}, {existing}"))
    return format_tags(parse_tags(f"{existing}, {generated}"))


def dataset_root(path: str) -> Path:
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise HTTPException(status_code=400, detail="dataset path is not a directory")
    return root


def resolve_image(root: Path, image: str) -> Path:
    image_path = (root / image).resolve()
    try:
        image_path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="image path is outside dataset root") from exc
    if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="unsupported image file")
    return image_path


def caption_path_for(image_path: Path) -> Path:
    return image_path.with_suffix(".txt")


def read_caption(image_path: Path) -> str:
    caption_path = caption_path_for(image_path)
    if not caption_path.is_file():
        return ""
    return caption_path.read_text(encoding="utf-8").strip()


def capture_caption(root: Path, image_path: Path) -> CaptionSnapshot:
    caption_path = caption_path_for(image_path)
    return CaptionSnapshot(
        image=normalize_relative_path(image_path.relative_to(root)),
        caption=read_caption(image_path),
        caption_exists=caption_path.is_file(),
    )


def remember_edit(root: Path, label: str, before: list[CaptionSnapshot], after: list[CaptionSnapshot]) -> None:
    if not before:
        return
    key = normalize_path(str(root))
    _UNDO_STACKS.setdefault(key, []).append(EditTransaction(label=label, before=before, after=after))
    _REDO_STACKS[key] = []


def restore_caption(root: Path, snapshot: CaptionSnapshot) -> dict:
    image_path = resolve_image(root, snapshot.image)
    caption_path = caption_path_for(image_path)
    if snapshot.caption_exists:
        write_caption(image_path, snapshot.caption)
    elif caption_path.exists():
        caption_path.unlink()
    caption = read_caption(image_path)
    return {
        "image": snapshot.image,
        "caption": caption,
        "caption_exists": caption_path.is_file(),
        "tags": parse_tags(caption),
    }


def snapshot_to_item(snapshot: CaptionSnapshot) -> dict:
    return {
        "image": snapshot.image,
        "caption": snapshot.caption,
        "caption_exists": snapshot.caption_exists,
        "tags": parse_tags(snapshot.caption),
    }


def transaction_to_change(tx: EditTransaction) -> dict:
    after_by_image = {item.image: item for item in tx.after}
    items = []
    for before in tx.before:
        after = after_by_image.get(before.image)
        items.append(
            {
                "image": before.image,
                "before": before.caption if before.caption_exists else "",
                "after": after.caption if after and after.caption_exists else "",
                "before_exists": before.caption_exists,
                "after_exists": bool(after and after.caption_exists),
            }
        )
    return {"label": tx.label, "count": len(items), "items": items}


def category_for(root: Path, image_path: Path) -> str:
    rel = image_path.relative_to(root)
    if len(rel.parts) <= 1:
        return ""
    return rel.parts[0]


def write_caption(image_path: Path, caption: str) -> str:
    normalized = caption.strip()
    caption_path_for(image_path).write_text(normalized, encoding="utf-8")
    return normalized


def image_to_data_url(image_path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(str(image_path))
    if not mime_type:
        mime_type = "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def build_chat_completions_url(endpoint: str) -> str:
    endpoint = endpoint.rstrip("/")
    if endpoint.endswith("/chat/completions"):
        return endpoint
    return f"{endpoint}/chat/completions"


def parse_api_caption(data: dict) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("API response does not contain choices[0].message.content") from exc
    if isinstance(content, str):
        caption = content.strip()
    elif isinstance(content, list):
        caption = " ".join(
            str(item.get("text", "")).strip()
            for item in content
            if isinstance(item, dict) and item.get("type") in {None, "text", "output_text"}
        ).strip()
    else:
        caption = ""
    if not caption:
        raise ValueError("API caption is empty")
    return caption


def generate_api_caption(image_path: Path, req: DatasetTagRequest) -> str:
    if not req.api_key.strip():
        raise HTTPException(status_code=400, detail="api_key is required for API tagging")
    if not req.api_model.strip():
        raise HTTPException(status_code=400, detail="api_model is required for API tagging")
    payload = {
        "model": req.api_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": req.api_prompt},
                    {"type": "image_url", "image_url": {"url": image_to_data_url(image_path)}},
                ],
            }
        ],
    }
    headers = {"Authorization": f"Bearer {req.api_key}"}
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with httpx.Client(timeout=60) as client:
                response = client.post(build_chat_completions_url(req.api_endpoint), headers=headers, json=payload)
            response.raise_for_status()
            return parse_api_caption(response.json())
        except Exception as exc:  # noqa: BLE001 - surface provider failures to UI
            last_error = exc
            if attempt >= 2:
                break
            time.sleep(min(2**attempt, 5))
    raise RuntimeError(f"API tagging failed for {image_path.name}: {last_error}") from last_error


def generate_local_tags(image_path: Path, req: DatasetTagRequest) -> str:
    if req.interrogator_model not in available_interrogators:
        raise HTTPException(status_code=400, detail=f"unknown tagger model: {req.interrogator_model}")
    interrogator = available_interrogators[req.interrogator_model]
    with use_download_endpoint(req.download_endpoint):
        ensure_interrogator_assets(req.interrogator_model, interrogator)
        with Image.open(image_path) as image:
            tags = interrogator.interrogate(image)
    processed = Interrogator.postprocess_tags(
        copy.deepcopy(tags),
        req.threshold,
        req.character_threshold,
        req.add_rating_tag,
        req.add_model_tag,
        parse_tags(req.additional_tags),
        parse_tags(req.exclude_tags),
        False,
        False,
        req.replace_underscore,
        [],
        req.escape_tag,
    )
    return format_tags(list(processed.keys()))


def scan_dataset(root: Path) -> dict:
    items = []
    tag_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    for image_path in sorted(root.rglob("*"), key=lambda p: normalize_path(str(p))):
        if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        rel = normalize_relative_path(image_path.relative_to(root))
        category = category_for(root, image_path)
        caption = read_caption(image_path)
        tags = parse_tags(caption)
        tag_counts.update(tags)
        category_counts.update([category])
        caption_path = caption_path_for(image_path)
        image_query = urlencode({"root": normalize_path(str(root)), "image": rel})
        items.append(
            {
                "name": image_path.name,
                "relative_path": rel,
                "category": category,
                "caption": caption,
                "caption_exists": caption_path.is_file(),
                "tags": tags,
                "image_url": f"/api/dataset-editor/image?{image_query}",
            }
        )
    return {
        "root": normalize_path(str(root)),
        "total": len(items),
        "items": items,
        "tags": [{"tag": tag, "count": count} for tag, count in sorted(tag_counts.items())],
        "categories": [
            {"name": category or "根目录", "value": category, "count": count}
            for category, count in sorted(category_counts.items())
        ],
    }


@router.post("/dataset-editor/scan")
async def scan(req: DatasetScanRequest):
    return APIResponseSuccess(data=scan_dataset(dataset_root(req.path)))


@router.get("/dataset-editor/image")
async def image(root: str, image: str):
    image_path = resolve_image(dataset_root(root), image)
    if not image_path.is_file():
        raise HTTPException(status_code=404, detail="image not found")
    return FileResponse(str(image_path))


@router.post("/dataset-editor/caption")
async def save_caption(req: CaptionWriteRequest):
    root = dataset_root(req.root)
    image_path = resolve_image(root, req.image)
    if not image_path.is_file():
        raise HTTPException(status_code=404, detail="image not found")
    before = capture_caption(root, image_path)
    caption = write_caption(image_path, req.caption)
    if before.caption != caption or not before.caption_exists:
        remember_edit(root, "保存当前 caption", [before], [capture_caption(root, image_path)])
    return APIResponseSuccess(
        data={
            "image": normalize_relative_path(image_path.relative_to(root)),
            "caption": caption,
            "caption_exists": caption_path_for(image_path).is_file(),
            "tags": parse_tags(caption),
        }
    )


@router.post("/dataset-editor/batch")
async def batch_edit(req: BatchEditRequest):
    root = dataset_root(req.root)
    append_tags = parse_tags(",".join(req.append))
    remove_tags = set(parse_tags(",".join(req.remove)))
    replacements = {item.source.strip(): item.target.strip() for item in req.replace if item.source.strip()}
    changed = 0
    results = []
    before_snapshots = []
    after_snapshots = []

    for rel in req.images:
        image_path = resolve_image(root, rel)
        if not image_path.is_file():
            continue
        tags = (
            normalize_caption_for_cleanup(
                read_caption(image_path),
                underscore_to_space=req.underscore_to_space,
                strip_escape_chars=req.strip_escape_chars,
            )
            if req.clean
            else parse_tags(read_caption(image_path))
        )
        next_tags = []
        for tag in tags:
            if tag in remove_tags:
                continue
            tag = replacements.get(tag, tag)
            if tag and tag not in next_tags:
                next_tags.append(tag)
        for tag in append_tags:
            if tag not in next_tags:
                next_tags.append(tag)
        if req.sort:
            next_tags = sorted(next_tags)
        next_caption = format_tags(next_tags)
        if next_caption != read_caption(image_path):
            before_snapshots.append(capture_caption(root, image_path))
            write_caption(image_path, next_caption)
            after_snapshots.append(capture_caption(root, image_path))
            changed += 1
        results.append(
            {
                "image": normalize_relative_path(image_path.relative_to(root)),
                "caption": next_caption,
                "caption_exists": caption_path_for(image_path).is_file(),
                "tags": next_tags,
            }
        )

    remember_edit(root, "批量编辑 caption", before_snapshots, after_snapshots)
    return APIResponseSuccess(data={"changed": changed, "items": results})


@router.post("/dataset-editor/tag")
async def tag_images(req: DatasetTagRequest):
    root = dataset_root(req.root)
    changed = 0
    skipped = 0
    failed = 0
    results = []
    before_snapshots = []
    after_snapshots = []

    for rel in req.images:
        image_path = resolve_image(root, rel)
        if not image_path.is_file():
            continue
        existing = read_caption(image_path)
        if existing and req.on_conflict == "ignore":
            skipped += 1
            results.append(snapshot_to_item(capture_caption(root, image_path)))
            continue
        try:
            generated = (
                generate_api_caption(image_path, req)
                if req.provider == "api"
                else generate_local_tags(image_path, req)
            )
            generated = format_tags(parse_tags(f"{generated}, {req.additional_tags}"))
            generated = format_tags([tag for tag in parse_tags(generated) if tag not in set(parse_tags(req.exclude_tags))])
            next_caption = merge_caption(existing, generated, req.on_conflict)
            if next_caption is None:
                skipped += 1
                continue
            if next_caption != existing:
                before_snapshots.append(capture_caption(root, image_path))
                write_caption(image_path, next_caption)
                after_snapshots.append(capture_caption(root, image_path))
                changed += 1
            results.append(snapshot_to_item(capture_caption(root, image_path)))
        except Exception:
            failed += 1
            raise

    label_provider = "API " if req.provider == "api" else "本地"
    label_kind = "自然语言" if req.caption_type == "caption" else "标签"
    remember_edit(root, f"{label_provider}{label_kind}打标", before_snapshots, after_snapshots)
    if req.provider == "local" and req.interrogator_model in available_interrogators:
        available_interrogators[req.interrogator_model].unload()
    return APIResponseSuccess(
        data={"changed": changed, "skipped": skipped, "failed": failed, "items": results}
    )


@router.post("/dataset-editor/undo")
async def undo(req: UndoRequest):
    root = dataset_root(req.root)
    stack = _UNDO_STACKS.get(normalize_path(str(root)), [])
    if not stack:
        return APIResponseSuccess(data={"changed": 0, "items": []}, message="nothing to undo")

    tx = stack.pop()
    _REDO_STACKS.setdefault(normalize_path(str(root)), []).append(tx)
    items = [restore_caption(root, snapshot) for snapshot in tx.before]
    return APIResponseSuccess(data={"changed": len(items), "items": items})


@router.post("/dataset-editor/redo")
async def redo(req: UndoRequest):
    root = dataset_root(req.root)
    key = normalize_path(str(root))
    stack = _REDO_STACKS.get(key, [])
    if not stack:
        return APIResponseSuccess(data={"changed": 0, "items": []}, message="nothing to redo")

    tx = stack.pop()
    _UNDO_STACKS.setdefault(key, []).append(tx)
    items = [restore_caption(root, snapshot) for snapshot in tx.after]
    return APIResponseSuccess(data={"changed": len(items), "items": items})


@router.post("/dataset-editor/history")
async def history(req: UndoRequest):
    root = dataset_root(req.root)
    key = normalize_path(str(root))
    undo_stack = _UNDO_STACKS.get(key, [])
    redo_stack = _REDO_STACKS.get(key, [])
    changes = [transaction_to_change(tx) for tx in reversed(undo_stack[-20:])]
    return APIResponseSuccess(
        data={
            "can_undo": bool(undo_stack),
            "can_redo": bool(redo_stack),
            "changes": changes,
        }
    )

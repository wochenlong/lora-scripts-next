from __future__ import annotations

import hashlib
import json
import math
import random
import secrets
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .errors import DatasetReviewError

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"})
CAPTION_EXTENSIONS = frozenset({".txt", ".caption", ".json", ".jsonl", ".csv", ".md"})
_TEXT_EXTENSIONS = CAPTION_EXTENSIONS
_REPARSE_ATTRIBUTE = 0x400


def _hash_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _hash_file(path: Path, chunk_size: int = 1024 * 1024) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(chunk_size):
                digest.update(chunk)
                total += len(chunk)
    except OSError as exc:
        raise DatasetReviewError("DATASET_READ_FAILED", "Dataset file could not be read.", details={"reason": str(exc)}) from None
    return "sha256:" + digest.hexdigest(), total


def _reject_reparse(path: Path) -> None:
    current = path
    while True:
        try:
            if current.is_symlink():
                raise DatasetReviewError("DATASET_REPARSE_REJECTED", "Dataset reparse points are not allowed.")
            attrs = getattr(current.stat(), "st_file_attributes", 0)
            if attrs & _REPARSE_ATTRIBUTE:
                raise DatasetReviewError("DATASET_REPARSE_REJECTED", "Dataset reparse points are not allowed.")
        except FileNotFoundError:
            pass
        if current.parent == current:
            return
        current = current.parent


def _root_path(root: str | Path) -> Path:
    if not isinstance(root, (str, Path)):
        raise DatasetReviewError("DATASET_ROOT_INVALID", "Dataset root is required.")
    value = Path(root).expanduser()
    if not value.is_absolute():
        value = value.absolute()
    try:
        value = value.resolve(strict=True)
    except OSError:
        raise DatasetReviewError("DATASET_ROOT_INVALID", "Dataset root could not be resolved.", status_code=404) from None
    if not value.is_dir():
        raise DatasetReviewError("DATASET_ROOT_INVALID", "Dataset root must be a directory.")
    _reject_reparse(value)
    return value


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(root).as_posix()
    except (OSError, ValueError):
        raise DatasetReviewError("DATASET_PATH_ESCAPE", "Dataset path escapes the selected root.") from None


def _image_dimensions(path: Path) -> tuple[int | None, int | None, str | None]:
    """Decode dimensions when Pillow is available; keep decode failures explicit."""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow is optional in lightweight hosts.
        return None, None, "IMAGE_DECODER_UNAVAILABLE"
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            return int(image.width), int(image.height), None
    except Exception as exc:
        return None, None, type(exc).__name__


@dataclass(frozen=True)
class InventoryItem:
    item_id: str
    relative_path: str
    kind: str
    bytes: int
    content_hash: str | None
    width: int | None = None
    height: int | None = None
    caption_path: str | None = None
    caption_hash: str | None = None
    caption_text: str | None = None
    decode_error: str | None = None
    read_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        # Consumer contracts use camelCase while retaining stable Python names.
        return {
            "itemId": value.pop("item_id"),
            "relativePath": value.pop("relative_path"),
            "kind": value.pop("kind"),
            "bytes": value.pop("bytes"),
            "contentHash": value.pop("content_hash"),
            "width": value.pop("width"),
            "height": value.pop("height"),
            "captionPath": value.pop("caption_path"),
            "captionHash": value.pop("caption_hash"),
            "captionText": value.pop("caption_text"),
            "decodeError": value.pop("decode_error"),
            "readError": value.pop("read_error"),
        }


@dataclass(frozen=True)
class DatasetInventory:
    root: str
    files: tuple[InventoryItem, ...]
    duplicate_groups: tuple[tuple[str, ...], ...]
    caption_distribution: Mapping[str, int]
    total_bytes: int
    scan_hash: str
    failures: tuple[dict[str, str], ...] = ()

    @property
    def images(self) -> tuple[InventoryItem, ...]:
        return tuple(item for item in self.files if item.kind == "image")

    @property
    def captions(self) -> tuple[InventoryItem, ...]:
        return tuple(item for item in self.files if item.kind == "caption")

    def as_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "files": [item.as_dict() for item in self.files],
            "images": len(self.images),
            "captions": len(self.captions),
            "duplicateGroups": [list(group) for group in self.duplicate_groups],
            "captionDistribution": dict(self.caption_distribution),
            "totalBytes": self.total_bytes,
            "scanHash": self.scan_hash,
            "failures": list(self.failures),
        }


def _caption_for_image(root: Path, image: Path) -> tuple[str | None, str | None, str | None]:
    # Sidecars are deterministic and never guessed outside the image directory.
    for extension in (".txt", ".caption", ".json"):
        candidate = image.with_suffix(extension)
        if not candidate.is_file():
            continue
        _reject_reparse(candidate)
        try:
            data = candidate.read_bytes()
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return _relative(root, candidate), _hash_bytes(data), None
        except OSError:
            return _relative(root, candidate), None, None
        return _relative(root, candidate), _hash_bytes(data), text
    return None, None, None


def inventory_dataset(root: str | Path, *, max_files: int | None = None) -> DatasetInventory:
    """Produce a sorted, deterministic read-only inventory of a dataset tree."""
    dataset_root = _root_path(root)
    files: list[InventoryItem] = []
    failures: list[dict[str, str]] = []
    count = 0
    review_overlay = dataset_root / ".agent-dataset-review"
    paths = sorted(
        (
            path
            for path in dataset_root.rglob("*")
            if path.is_file() and not (path == review_overlay or review_overlay in path.parents)
        ),
        key=lambda p: _relative(dataset_root, p),
    )
    for path in paths:
        relative = _relative(dataset_root, path)
        if max_files is not None and count >= max_files:
            failures.append({"path": relative, "code": "DATASET_LIMIT_EXCEEDED"})
            continue
        count += 1
        _reject_reparse(path)
        suffix = path.suffix.casefold()
        kind = "image" if suffix in IMAGE_EXTENSIONS else "caption" if suffix in CAPTION_EXTENSIONS else "other"
        digest: str | None = None
        size = 0
        read_error: str | None = None
        try:
            digest, size = _hash_file(path)
        except DatasetReviewError as exc:
            read_error = exc.code
            failures.append({"path": relative, "code": exc.code})
        width = height = None
        decode_error = None
        caption_path = caption_hash = caption_text = None
        if kind == "image" and read_error is None:
            width, height, decode_error = _image_dimensions(path)
            caption_path, caption_hash, caption_text = _caption_for_image(dataset_root, path)
            if decode_error:
                failures.append({"path": relative, "code": decode_error})
        item_id = "sha256:" + hashlib.sha256(relative.encode("utf-8")).hexdigest()
        files.append(InventoryItem(item_id, relative, kind, size, digest, width, height, caption_path, caption_hash, caption_text, decode_error, read_error))
    duplicate_map: dict[str, list[str]] = {}
    for item in files:
        if item.kind == "image" and item.content_hash:
            duplicate_map.setdefault(item.content_hash, []).append(item.relative_path)
    duplicate_groups = tuple(tuple(paths) for _, paths in sorted(duplicate_map.items()) if len(paths) > 1)
    distribution: dict[str, int] = {"withCaption": 0, "withoutCaption": 0, "invalidCaption": 0}
    for item in files:
        if item.kind != "image":
            continue
        if item.caption_path is None:
            distribution["withoutCaption"] += 1
        elif item.caption_text is None:
            distribution["invalidCaption"] += 1
        else:
            distribution["withCaption"] += 1
    canonical = {
        "files": [item.as_dict() for item in files],
        "duplicates": [list(group) for group in duplicate_groups],
        "distribution": distribution,
        "failures": failures,
    }
    scan_hash = _hash_bytes(json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return DatasetInventory(str(dataset_root), tuple(files), duplicate_groups, distribution, sum(item.bytes for item in files), scan_hash, tuple(failures))


def select_review_sample(inventory: DatasetInventory, *, limit: int = 12, seed: str = "dataset-review-v1") -> tuple[InventoryItem, ...]:
    """Select deterministic samples, prioritising failures and duplicate groups."""
    if limit < 0:
        raise DatasetReviewError("DATASET_SAMPLE_INVALID", "Sample limit must be non-negative.")
    images = list(inventory.images)
    priority = [item for item in images if item.decode_error or item.caption_path is None]
    duplicate_paths = {path for group in inventory.duplicate_groups for path in group}
    priority.extend(item for item in images if item.relative_path in duplicate_paths and item not in priority)
    remaining = [item for item in images if item not in priority]
    random.Random(seed).shuffle(remaining)
    selected: list[InventoryItem] = []
    for item in priority + remaining:
        if item not in selected:
            selected.append(item)
        if len(selected) >= limit:
            break
    return tuple(selected)


@dataclass(frozen=True)
class ActiveModelCapability:
    """Capability reported by the one active remote model for this session."""

    model: str
    vision: bool
    capabilities: tuple[str, ...] = ("text",)
    profile_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"model": self.model, "vision": self.vision, "capabilities": list(self.capabilities), "profileId": self.profile_id}


@dataclass(frozen=True)
class ImageReviewResult:
    item_id: str
    relative_path: str
    status: str
    findings: tuple[dict[str, Any], ...] = ()
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"itemId": self.item_id, "relativePath": self.relative_path, "status": self.status, "findings": list(self.findings), "reason": self.reason}


@dataclass(frozen=True)
class DatasetReviewReport:
    status: str
    capability: Mapping[str, Any]
    total_images: int
    sampled_images: int
    reviewed_images: int
    unreviewed_images: int
    results: tuple[ImageReviewResult, ...]
    limitations: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "capability": dict(self.capability), "totalImages": self.total_images, "sampledImages": self.sampled_images, "reviewedImages": self.reviewed_images, "unreviewedImages": self.unreviewed_images, "results": [result.as_dict() for result in self.results], "limitations": list(self.limitations)}


RemoteReviewer = Callable[[InventoryItem, ActiveModelCapability], Mapping[str, Any] | Sequence[Mapping[str, Any]]]


def review_images(inventory: DatasetInventory, sample: Iterable[InventoryItem], capability: ActiveModelCapability, reviewer: RemoteReviewer | None = None) -> DatasetReviewReport:
    """Review selected images using the current remote model only.

    A text-only capability follows the same generic unavailable path regardless
    of provider/model name and never fabricates visual findings.
    """
    selected = tuple(sample)
    if any(item not in inventory.images for item in selected):
        raise DatasetReviewError("DATASET_SAMPLE_INVALID", "Review sample contains an item outside the inventory.")
    if not capability.vision:
        results = tuple(ImageReviewResult(item.item_id, item.relative_path, "unavailable", reason="MODEL_CAPABILITY_UNAVAILABLE") for item in selected)
        return DatasetReviewReport("MODEL_CAPABILITY_UNAVAILABLE", capability.as_dict(), len(inventory.images), len(selected), 0, len(inventory.images), results, ("The active model does not advertise image capability.",))
    if reviewer is None:
        raise DatasetReviewError("REMOTE_REVIEWER_REQUIRED", "An approved remote reviewer is required for image-capable review.")
    results: list[ImageReviewResult] = []
    for item in selected:
        try:
            raw = reviewer(item, capability)
            findings = tuple(raw if isinstance(raw, Sequence) and not isinstance(raw, Mapping) else (raw,))
            results.append(ImageReviewResult(item.item_id, item.relative_path, "reviewed", tuple(dict(entry) for entry in findings if isinstance(entry, Mapping))))
        except Exception as exc:
            results.append(ImageReviewResult(item.item_id, item.relative_path, "unavailable", reason="REMOTE_REVIEW_FAILED"))
    reviewed = sum(result.status == "reviewed" for result in results)
    status = "complete" if reviewed == len(selected) else "partial"
    return DatasetReviewReport(status, capability.as_dict(), len(inventory.images), len(selected), reviewed, len(inventory.images) - reviewed, tuple(results), ("Only the selected sample was reviewed; remaining images are unreviewed.",))


__all__ = ["ActiveModelCapability", "DatasetInventory", "DatasetReviewReport", "ImageReviewResult", "InventoryItem", "inventory_dataset", "review_images", "select_review_sample"]

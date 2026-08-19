"""HTTP API for the products (artifact) management feature.

Mounted under ``/api`` alongside the main router. Everything here is
read-only against the filesystem: listing, manual scan, detail. Actions
(resize/merge/extract), deploy and metadata editing live in their own
modules (see docs/需求-制品管理.md).
"""

from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from mikazuki.app.models import APIResponseFail, APIResponseSuccess
from mikazuki.log import log
from mikazuki.products.registry import default_registry
from mikazuki.products.scanner import collect_products, resolve_output_path
from mikazuki.utils.train_utils import read_safetensors_metadata

router = APIRouter()


class ProductScanRequest(BaseModel):
    dirs: List[str] = Field(default_factory=list)


def _find_product(product_id: str) -> Optional[dict]:
    listing = collect_products(default_registry())
    for group in listing["groups"]:
        for product in group["products"]:
            if product["id"] == product_id:
                return product
    return None


@router.get("/products")
async def list_products(family: Optional[str] = None):
    try:
        listing = collect_products(default_registry())
    except Exception as exc:  # noqa: BLE001 - registry corruption must not break the API
        log.warning(f"products listing failed: {exc}")
        return APIResponseFail(message=f"制品列表加载失败: {exc}")
    groups = listing["groups"]
    if family:
        groups = [g for g in groups if g["family"] == family]
    return APIResponseSuccess(data={
        "groups": groups,
        "families": listing["families"],
        "scanned_dirs": listing["scanned_dirs"],
    })


@router.post("/products/scan")
async def scan_products(req: ProductScanRequest):
    registry = default_registry()
    added: List[str] = []
    for d in req.dirs:
        directory = Path(d)
        if not directory.is_dir():
            return APIResponseFail(message=f"目录不存在: {d}")
        added.append(registry.add_scan_dir(directory))
    try:
        listing = collect_products(registry)
    except Exception as exc:  # noqa: BLE001
        log.warning(f"products scan failed: {exc}")
        return APIResponseFail(message=f"制品扫描失败: {exc}")
    total = sum(len(g["products"]) for g in listing["groups"])
    return APIResponseSuccess(data={
        "scanned_dirs": listing["scanned_dirs"],
        "added_dirs": added,
        "total": total,
    })


@router.get("/products/runs")
async def list_runs():
    return APIResponseSuccess(data={"runs": default_registry().list_runs()})


@router.get("/products/resolve-path")
async def resolve_path_endpoint(path: str):
    """F5a: resolve a (possibly relative) path against the server cwd."""
    resolved = resolve_output_path(path)
    return APIResponseSuccess(data={"path": path, "resolved": resolved})


@router.get("/products/{product_id}")
async def product_detail(product_id: str):
    product = _find_product(product_id)
    if product is None:
        return APIResponseFail(message="制品不存在（可能已被移动或删除，重新扫描试试）")

    detail = dict(product)
    if product["status"] == "present":
        try:
            header = read_safetensors_metadata(product["path"]) or {}
            detail["metadata"] = header.get("__metadata__", {}) if isinstance(header, dict) else {}
        except Exception as exc:  # noqa: BLE001
            log.warning(f"Failed to read product metadata for {product['path']}: {exc}")
            detail["metadata"] = {}

    registry = default_registry()
    run = None
    if product.get("run_task_id"):
        run = registry.runs.get(product["run_task_id"])
    if run:
        config_path = run.get("config_path")
        detail["run"] = {
            **run,
            "config_exists": bool(config_path) and Path(config_path).is_file(),
        }
    else:
        detail["run"] = None
    return APIResponseSuccess(data={"product": detail})

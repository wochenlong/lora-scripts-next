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
from mikazuki.products import deploy as deploy_mod
from mikazuki.products.registry import default_registry
from mikazuki.products.scanner import collect_products, resolve_output_path
from mikazuki.utils.train_utils import read_safetensors_metadata

router = APIRouter()


class ProductScanRequest(BaseModel):
    dirs: List[str] = Field(default_factory=list)


class DeployRequest(BaseModel):
    target: str
    method: str = "copy"


class UndeployRequest(BaseModel):
    target: str


class DeployTargetRequest(BaseModel):
    name: str
    path: str


def _find_product(product_id: str) -> Optional[dict]:
    listing = collect_products(default_registry())
    for group in listing["groups"]:
        for product in group["products"]:
            if product["id"] == product_id:
                return product
    return None


def _with_deploy_status(product: dict, targets: dict) -> dict:
    """Attach read-only per-target deployment status (ok/missing/conflict...)."""
    deployed_to = product.get("deployed_to") or {}
    status: dict = {}
    for name, entry in deployed_to.items():
        try:
            outcome = deploy_mod.check_entry(entry)
            status[name] = outcome["status"]
            if outcome.get("message"):
                status[f"{name}__message"] = outcome["message"]
        except Exception as exc:  # noqa: BLE001
            status[name] = f"error: {exc}"
    product["deploy_status"] = status
    product["deploy_targets_known"] = [n for n in deployed_to if n in targets]
    return product


@router.get("/products")
async def list_products(family: Optional[str] = None):
    try:
        listing = collect_products(default_registry())
    except Exception as exc:  # noqa: BLE001 - registry corruption must not break the API
        log.warning(f"products listing failed: {exc}")
        return APIResponseFail(message=f"制品列表加载失败: {exc}")
    groups = listing["groups"]
    targets = deploy_mod.load_targets()
    for group in groups:
        group["products"] = [
            _with_deploy_status(p, targets) if p.get("deployed_to") else p
            for p in group["products"]
        ]
    if family:
        groups = [g for g in groups if g["family"] == family]
    return APIResponseSuccess(data={
        "groups": groups,
        "families": listing["families"],
        "scanned_dirs": listing["scanned_dirs"],
        "deploy_targets": targets,
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


# ---- deploy targets (declared before /products/{product_id} to win routing) ----


@router.get("/products/deploy/targets")
async def get_deploy_targets():
    return APIResponseSuccess(data={"targets": deploy_mod.load_targets()})


@router.post("/products/deploy/targets")
async def add_deploy_target(req: DeployTargetRequest):
    name = req.name.strip()
    if not name:
        return APIResponseFail(message="目标名称不能为空")
    directory = Path(req.path)
    if not directory.is_dir():
        return APIResponseFail(message=f"目录不存在: {req.path}")
    targets = deploy_mod.load_targets()
    targets[name] = str(directory.resolve())
    deploy_mod.save_targets(targets)
    return APIResponseSuccess(data={"targets": targets})


@router.delete("/products/deploy/targets/{name}")
async def remove_deploy_target(name: str):
    targets = deploy_mod.load_targets()
    if name not in targets:
        return APIResponseFail(message=f"目标不存在: {name}")
    del targets[name]
    deploy_mod.save_targets(targets)
    return APIResponseSuccess(data={"targets": targets})


@router.post("/products/deploy/reconcile")
async def reconcile_deployments():
    registry = default_registry()
    try:
        results = deploy_mod.reconcile_all(registry, deploy_mod.load_targets())
    except Exception as exc:  # noqa: BLE001
        log.warning(f"deploy reconcile failed: {exc}")
        return APIResponseFail(message=f"部署对账失败: {exc}")
    return APIResponseSuccess(data={"results": results})


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
    return APIResponseSuccess(data={"product": _with_deploy_status(detail, deploy_mod.load_targets())})


@router.post("/products/{product_id}/deploy")
async def deploy_product(product_id: str, req: DeployRequest):
    product = _find_product(product_id)
    if product is None or product["status"] != "present":
        return APIResponseFail(message="制品不存在或文件缺失")
    targets = deploy_mod.load_targets()
    if req.target not in targets:
        return APIResponseFail(message=f"部署目标不存在: {req.target}")
    try:
        result = deploy_mod.deploy_product(
            default_registry(),
            product_path=product["path"],
            product_family=product["family"],
            target_name=req.target,
            target_dir=targets[req.target],
            method=req.method,
        )
    except FileExistsError as exc:
        return APIResponseFail(message=str(exc), data={"conflict": True})
    except (OSError, FileNotFoundError) as exc:
        return APIResponseFail(message=f"部署失败: {exc}")
    return APIResponseSuccess(data=result)


@router.post("/products/{product_id}/undeploy")
async def undeploy_product(product_id: str, req: UndeployRequest):
    product = _find_product(product_id)
    if product is None:
        return APIResponseFail(message="制品不存在")
    result = deploy_mod.undeploy_product(
        default_registry(), product_path=product["path"], target_name=req.target,
    )
    if result.get("status") == "not_deployed":
        return APIResponseFail(message=f"该制品未部署到 {req.target}")
    return APIResponseSuccess(data=result)


@router.delete("/products/{product_id}")
async def delete_product(product_id: str):
    product = _find_product(product_id)
    if product is None:
        return APIResponseFail(message="制品不存在")
    deployed_to = product.get("deployed_to") or {}
    active = [name for name, e in deployed_to.items() if e.get("desired") == "deployed"]
    if active:
        return APIResponseFail(
            message=f"该制品仍声明部署在 {', '.join(active)}，请先下架",
            data={"deployed_to": active},
        )
    if product["status"] == "present":
        try:
            Path(product["path"]).unlink()
        except OSError as exc:
            return APIResponseFail(message=f"删除文件失败: {exc}")
    default_registry().clear_product_state(product_id)
    return APIResponseSuccess(data={"deleted": product["path"]})

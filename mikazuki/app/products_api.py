"""HTTP API for the products (artifact) management feature.

Mounted under ``/api`` alongside the main router. Listing/scan/detail are
read-only; deploy, metadata editing and actions (resize/merge/extract) live
in their own mikazuki.products modules (see docs/需求-制品管理.md).
"""

import json
import tomllib
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from mikazuki.app.models import APIResponseFail, APIResponseSuccess
from mikazuki.log import log
from mikazuki.products import actions as actions_mod
from mikazuki.products import deploy as deploy_mod
from mikazuki.products import meta_editor
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


class MetadataUpdateRequest(BaseModel):
    metadata: dict


class ResizeRequest(BaseModel):
    output_path: str
    new_rank: Optional[int] = None
    new_conv_rank: Optional[int] = None
    dynamic_method: Optional[str] = None
    dynamic_param: Optional[float] = None
    save_precision: Optional[str] = None


class MergeRequest(BaseModel):
    inputs: List[str]
    ratios: List[float]
    output_path: str
    concat: bool = False
    shuffle: bool = False


class ExtractRequest(BaseModel):
    model_org: str
    output_path: str
    dim: int
    conv_dim: Optional[int] = None
    sdxl: bool = False
    v2: bool = False


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


@router.get("/products/{product_id}/download")
async def download_product(product_id: str):
    """F14: HTTP download for remote work scenarios. Small files (LoRA, sample
    images, logs) go through this channel; the UI warns on large files."""
    product = _find_product(product_id)
    if product is None or product["status"] != "present":
        raise HTTPException(status_code=404, detail="product not found")
    return FileResponse(product["path"], filename=product["name"])


@router.put("/products/{product_id}/metadata")
async def update_metadata(product_id: str, req: MetadataUpdateRequest):
    """F12': rewrite the safetensors __metadata__ section (tensor bytes are
    never touched; original backed up to .bak on first edit)."""
    product = _find_product(product_id)
    if product is None or product["status"] != "present":
        return APIResponseFail(message="制品不存在或文件缺失")
    try:
        result = meta_editor.write_metadata(product["path"], req.metadata)
    except meta_editor.MetadataEditError as exc:
        return APIResponseFail(message=str(exc))
    except Exception as exc:  # noqa: BLE001
        log.warning(f"metadata edit failed for {product['path']}: {exc}")
        return APIResponseFail(message=f"metadata 保存失败: {exc}")
    return APIResponseSuccess(data=result)


# ---- product actions (experimental): resize / merge / extract ----


@router.post("/products/{product_id}/actions/resize")
async def resize_product(product_id: str, req: ResizeRequest):
    product = _find_product(product_id)
    if product is None or product["status"] != "present":
        return APIResponseFail(message="制品不存在或文件缺失")
    if product.get("train_type") and "musubi" in str(product["train_type"]):
        return APIResponseFail(message="musubi 制品暂不支持 resize")
    try:
        result = actions_mod.submit_resize(
            default_registry(),
            source=product["path"],
            output_path=req.output_path,
            new_rank=req.new_rank,
            new_conv_rank=req.new_conv_rank,
            dynamic_method=req.dynamic_method,
            dynamic_param=req.dynamic_param,
            save_precision=req.save_precision,
        )
    except actions_mod.ActionError as exc:
        return APIResponseFail(message=str(exc))
    return APIResponseSuccess(data=result)


@router.post("/products/actions/merge")
async def merge_products(req: MergeRequest):
    registry = default_registry()
    sources: List[str] = []
    for pid in req.inputs:
        product = _find_product(pid)
        if product is None or product["status"] != "present":
            return APIResponseFail(message=f"制品不存在或文件缺失: {pid}")
        if product.get("is_lycoris"):
            return APIResponseFail(message=f"{product['name']} 是 LyCORIS 格式，无法直接 merge")
        sources.append(product["path"])
    try:
        result = actions_mod.submit_merge(
            registry, sources=sources, ratios=req.ratios, output_path=req.output_path,
            concat=req.concat, shuffle=req.shuffle,
        )
    except actions_mod.ActionError as exc:
        return APIResponseFail(message=str(exc))
    return APIResponseSuccess(data=result)


@router.post("/products/{product_id}/actions/extract")
async def extract_product(product_id: str, req: ExtractRequest):
    product = _find_product(product_id)
    if product is None or product["status"] != "present":
        return APIResponseFail(message="制品不存在或文件缺失")
    try:
        result = actions_mod.submit_extract(
            default_registry(),
            model_org=req.model_org,
            model_tuned=product["path"],
            output_path=req.output_path,
            dim=req.dim,
            conv_dim=req.conv_dim,
            sdxl=req.sdxl,
            v2=req.v2,
        )
    except actions_mod.ActionError as exc:
        return APIResponseFail(message=str(exc))
    return APIResponseSuccess(data=result)


# ---- F11: refill training form from a product ----

_SS_TO_CONFIG = {
    "ss_network_dim": "network_dim",
    "ss_network_alpha": "network_alpha",
    "ss_network_module": "network_module",
    "ss_learning_rate": "learning_rate",
    "ss_unet_lr": "unet_lr",
    "ss_text_encoder_lr": "text_encoder_lr",
    "ss_lr_scheduler": "lr_scheduler",
    "ss_optimizer": "optimizer_type",
    "ss_max_train_epochs": "max_train_epochs",
    "ss_resolution": "resolution",
}

_FAMILY_TO_TRAIN_TYPE = {
    "sdxl": "sdxl-lora",
    "sd3": "sd3-lora",
    "flux": "flux-lora",
    "sd": "sd-lora",
}


def _config_from_ss_metadata(metadata: dict, family: str) -> dict:
    """Best-effort core-field mapping from ss_* metadata (snapshot absent)."""
    config: dict = {"model_train_type": _FAMILY_TO_TRAIN_TYPE.get(family, "sd-lora")}
    for ss_key, config_key in _SS_TO_CONFIG.items():
        value = metadata.get(ss_key)
        if value is None:
            continue
        if config_key in ("network_dim", "max_train_epochs"):
            try:
                value = int(value)
            except (TypeError, ValueError):
                continue
        elif config_key == "network_alpha":
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
        config[config_key] = value
    return config


@router.get("/products/{product_id}/training-config")
async def product_training_config(product_id: str):
    """F11: config for "train again with these params". Prefers the linked
    run's autosave snapshot (exact); falls back to core ss_* fields."""
    product = _find_product(product_id)
    if product is None:
        return APIResponseFail(message="制品不存在")

    registry = default_registry()
    run = registry.runs.get(product.get("run_task_id") or "")
    config_path = (run or {}).get("config_path")
    if config_path and Path(config_path).is_file():
        try:
            with open(config_path, "rb") as f:
                config = tomllib.load(f)
            if run.get("train_type"):
                config["model_train_type"] = run["train_type"]
            return APIResponseSuccess(data={"source": "snapshot", "config": config})
        except (tomllib.TOMLDecodeError, OSError) as exc:
            log.warning(f"failed to parse config snapshot {config_path}: {exc}")

    metadata = {}
    if product["status"] == "present":
        try:
            header = read_safetensors_metadata(product["path"]) or {}
            metadata = header.get("__metadata__", {}) if isinstance(header, dict) else {}
        except Exception as exc:  # noqa: BLE001
            log.warning(f"failed to read metadata for refill: {exc}")
    if not metadata:
        return APIResponseFail(message="该制品没有可用的配置快照或 ss_* 参数")
    config = _config_from_ss_metadata(metadata, product.get("family") or "other")
    return APIResponseSuccess(data={"source": "metadata", "config": config})

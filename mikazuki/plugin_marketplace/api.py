from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .manager import MarketplaceManager
from .models import MarketplaceEntry
from .paths import MarketplacePaths
from .store import MarketplaceStore
from .trust import TrustStore


router = APIRouter(prefix="/marketplace", tags=["plugin-marketplace"])
host_router = APIRouter(prefix="/plugin-host", tags=["plugin-host"])


class _RequestModel(BaseModel):
    class Config:
        extra = "forbid"


class InstallRequest(_RequestModel):
    entry: MarketplaceEntry


class RollbackRequest(_RequestModel):
    version: str | None = None


class UninstallRequest(_RequestModel):
    """Ordinary uninstall accepts no destructive data-retention options."""


def _host_version() -> str:
    version_file = Path(__file__).resolve().parents[2] / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


def _platform_name() -> str:
    machine = os.environ.get("PROCESSOR_ARCHITECTURE", "").casefold()
    arch = "arm64" if "arm64" in machine else "x64"
    if sys.platform == "win32":
        return f"win32-{arch}"
    if sys.platform.startswith("linux"):
        return f"linux-{arch}"
    return f"{sys.platform}-{arch}"


def _default_manager() -> MarketplaceManager:
    configured = os.environ.get("MIKAZUKI_PLUGIN_MARKETPLACE_ROOT", "").strip()
    root = Path(configured).resolve() if configured else (Path.cwd() / ".runtime" / "plugin-marketplace").resolve()
    paths = MarketplacePaths(root)
    # Production trust roots are release-governed.  An empty root keeps status,
    # uninstall and core startup available while making every install fail closed.
    return MarketplaceManager(
        paths=paths,
        store=MarketplaceStore(paths.registry_file),
        trust=TrustStore({}),
        host_version=_host_version(),
        platform=_platform_name(),
    )


_manager = _default_manager()


def configure_marketplace(manager: MarketplaceManager) -> None:
    """Inject a release-configured manager (or a deterministic test manager)."""
    global _manager
    _manager = manager


def _success(data) -> dict:
    return {"status": "success", "data": data}


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(
            status_code=404,
            detail={
                "code": "MARKETPLACE_NOT_FOUND",
                "message": "Requested marketplace resource was not found.",
            },
        )
    if isinstance(exc, PermissionError):
        return HTTPException(
            status_code=403,
            detail={
                "code": "MARKETPLACE_FORBIDDEN",
                "message": "Marketplace operation is not permitted.",
            },
        )
    return HTTPException(
        status_code=400,
        detail={
            "code": "MARKETPLACE_REQUEST_INVALID",
            "message": "Marketplace request could not be completed.",
        },
    )


@router.get("/plugins")
async def list_plugins():
    return _success([status.model_dump(mode="json") for status in _manager.list_statuses()])


@router.get("/plugins/{plugin_id}")
async def plugin_status(plugin_id: str):
    try:
        return _success(_manager.status(plugin_id).model_dump(mode="json"))
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/plugins/{plugin_id}/install")
async def install_plugin(plugin_id: str, request: InstallRequest):
    if request.entry.id != plugin_id:
        raise _http_error(ValueError("catalog entry id does not match route plugin id"))
    try:
        package = _manager.paths.quarantine_package(plugin_id, request.entry.latest_version)
        status = _manager.install(request.entry, package)
        return _success(status.model_dump(mode="json"))
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/plugins/{plugin_id}/enable")
async def enable_plugin(plugin_id: str):
    try:
        return _success(_manager.enable(plugin_id).model_dump(mode="json"))
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/plugins/{plugin_id}/disable")
async def disable_plugin(plugin_id: str):
    try:
        return _success(_manager.disable(plugin_id).model_dump(mode="json"))
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/plugins/{plugin_id}/rollback")
async def rollback_plugin(plugin_id: str, request: RollbackRequest):
    try:
        return _success(_manager.rollback(plugin_id, request.version).model_dump(mode="json"))
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/plugins/{plugin_id}/uninstall")
async def uninstall_plugin(plugin_id: str, request: UninstallRequest):
    try:
        status = _manager.uninstall(plugin_id)
        return _success(status.model_dump(mode="json"))
    except Exception as exc:
        raise _http_error(exc) from exc


@host_router.get("/extensions")
async def enabled_extensions():
    return _success({"extensions": _manager.enabled_extensions()})


@host_router.get("/ui/{plugin_id}/{version}/{asset_path:path}")
async def plugin_ui_artifact(plugin_id: str, version: str, asset_path: str):
    try:
        return FileResponse(
            _manager.ui_artifact(plugin_id, version, asset_path),
            headers={
                "Content-Security-Policy": (
                    "default-src 'none'; "
                    "script-src 'self'; "
                    "style-src 'self' 'unsafe-inline'; "
                    "img-src 'self' data: blob:; "
                    "font-src 'self'; "
                    "connect-src 'none'; "
                    "object-src 'none'; "
                    "base-uri 'none'; "
                    "form-action 'none'"
                ),
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "public, max-age=31536000, immutable",
            },
        )
    except Exception as exc:
        raise _http_error(exc) from exc


__all__ = ["configure_marketplace", "host_router", "router"]

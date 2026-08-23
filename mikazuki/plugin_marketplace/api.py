from __future__ import annotations

import os
import secrets
import sys
import json
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, validator

from mikazuki.plugin_host import (
    AgentRouteAuthority,
    AgentRouteAuthorityConfig,
    CapabilityBrokerError,
    ConfirmationError,
    ConfirmationTicketStore,
    ExecutablePluginRuntime,
    PluginCapabilityBroker,
)
from mikazuki.plugin_host.agent_tools import configure_agent_tool_service

from .manager import MarketplaceManager
from .models import MarketplaceEntry
from .catalog import CatalogError, MarketplaceCatalogService
from .paths import MarketplacePaths
from .store import MarketplaceStore
from .trust import TrustError, TrustStore


router = APIRouter(prefix="/marketplace", tags=["plugin-marketplace"])
host_router = APIRouter(prefix="/plugin-host", tags=["plugin-host"])


class _RequestModel(BaseModel):
    class Config:
        extra = "forbid"
        allow_population_by_field_name = True


class InstallRequest(_RequestModel):
    version: str | None = None
    approved_permissions: list[str] = Field(default_factory=list, alias="approvedPermissions")

    _unique_permissions = validator("approved_permissions", allow_reuse=True)(
        lambda value: _validate_unique_permissions(value)
    )


class EnableRequest(_RequestModel):
    permissions: list[str]

    _unique_permissions = validator("permissions", allow_reuse=True)(
        lambda value: _validate_unique_permissions(value)
    )


class RollbackRequest(_RequestModel):
    version: str | None = None


class UninstallRequest(_RequestModel):
    """Ordinary uninstall accepts no destructive data-retention options."""


class RestartRequest(_RequestModel):
    pass


class BootstrapRequest(_RequestModel):
    pass


class BrokerRequest(_RequestModel):
    request_id: str = Field(alias="requestId")
    method: str
    params: dict[str, Any]

    @validator("request_id")
    def validate_request_id(cls, value: str) -> str:
        import uuid

        try:
            parsed = uuid.UUID(value)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("requestId must be a UUID") from exc
        if str(parsed) != value.casefold():
            raise ValueError("requestId must use canonical UUID syntax")
        return value

    @validator("method")
    def validate_method(cls, value: str) -> str:
        import re

        if len(value) > 128 or not re.fullmatch(r"[a-z][a-z0-9-]*(?:\.[A-Za-z][A-Za-z0-9-]*)+", value):
            raise ValueError("method must be a namespaced identifier")
        return value


class ConfirmationResolutionRequest(_RequestModel):
    decision: Literal["approved", "rejected"]


def _validate_unique_permissions(value: list[str]) -> list[str]:
    if len(value) != len(set(value)):
        raise ValueError("duplicate permission approvals are forbidden")
    return value


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
    port = os.environ.get("MIKAZUKI_PORT", "28000").strip()
    # Production trust roots are release-governed.  An empty root keeps status,
    # uninstall and core startup available while making every install fail closed.
    return MarketplaceManager(
        paths=paths,
        store=MarketplaceStore(paths.registry_file),
        trust=TrustStore({}),
        host_version=_host_version(),
        platform=_platform_name(),
        runtime=ExecutablePluginRuntime(
            # The sidecar appends /internal/agent-tools/... itself; the app
            # mounts the agent-tools router under the /api prefix.
            host_tool_base_url=f"http://127.0.0.1:{port}/api",
        ),
    )


_manager = _default_manager()
_catalog = MarketplaceCatalogService(paths=_manager.paths, trust=_manager.trust)
_confirmations = ConfirmationTicketStore()
configure_agent_tool_service(_confirmations)


def _confirmation_capability_error(exc: ConfirmationError) -> CapabilityBrokerError:
    return CapabilityBrokerError(
        exc.code,
        exc.public_message,
        status_code=exc.status_code,
    )


def _install_confirmation_handlers(broker: PluginCapabilityBroker) -> None:
    broker.unregister("confirmation.request")
    broker.unregister("confirmation.getResult")

    def request_confirmation(context, params):
        if set(params) != {"toolCallId"} or not isinstance(params.get("toolCallId"), str) or not params["toolCallId"]:
            raise CapabilityBrokerError(
                "PLUGIN_CAPABILITY_PARAMS_INVALID",
                "The plugin capability parameters are invalid.",
            )
        try:
            return _confirmations.request_projection(
                plugin_id=context.plugin_id,
                tool_call_id=params["toolCallId"],
                granted_permissions=context.granted_permissions,
            )
        except ConfirmationError as exc:
            raise _confirmation_capability_error(exc) from None

    def get_confirmation_result(context, params):
        if set(params) != {"ticketId"} or not isinstance(params.get("ticketId"), str) or not params["ticketId"]:
            raise CapabilityBrokerError(
                "PLUGIN_CAPABILITY_PARAMS_INVALID",
                "The plugin capability parameters are invalid.",
            )
        try:
            return _confirmations.result(
                plugin_id=context.plugin_id,
                ticket_id=params["ticketId"],
                granted_permissions=context.granted_permissions,
            )
        except ConfirmationError as exc:
            raise _confirmation_capability_error(exc) from None

    broker.register_dynamic_request("confirmation.request", request_confirmation)
    broker.register_dynamic_request("confirmation.getResult", get_confirmation_result)


_broker = PluginCapabilityBroker()
_install_confirmation_handlers(_broker)


def _default_authority_config() -> AgentRouteAuthorityConfig | None:
    host = os.environ.get("MIKAZUKI_HOST", "127.0.0.1").strip()
    port = os.environ.get("MIKAZUKI_PORT", "28000").strip()
    authority_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    authority = f"{authority_host}:{port}"
    try:
        return AgentRouteAuthorityConfig(
            allowed_hosts={authority},
            allowed_origins={f"http://{authority}"},
            run_token=secrets.token_urlsafe(32),
        )
    except ValueError:
        # --listen/non-loopback mode intentionally has no Agent authority.
        return None


_authority_config = _default_authority_config()


def configure_marketplace(manager: MarketplaceManager) -> None:
    """Inject a release-configured manager (or a deterministic test manager)."""
    global _manager
    _manager = manager


def configure_marketplace_catalog(catalog: MarketplaceCatalogService) -> None:
    global _catalog
    _catalog = catalog


def configure_capability_broker(broker: PluginCapabilityBroker) -> None:
    global _broker
    _install_confirmation_handlers(broker)
    _broker = broker


def configure_confirmation_store(store: ConfirmationTicketStore) -> None:
    global _confirmations
    _confirmations = store


def get_confirmation_store() -> ConfirmationTicketStore:
    """Trusted Host services use this to create tickets before plugin projection."""
    return _confirmations


def configure_marketplace_authority(config: AgentRouteAuthorityConfig | None) -> None:
    global _authority_config
    _authority_config = config


async def _require_mutation_authority(request: Request):
    if _authority_config is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "AGENT_ROUTE_FORBIDDEN", "reason": "disabled"},
        )
    return await AgentRouteAuthority.for_json_mutation(_authority_config)(request)


async def _require_bootstrap_authority(request: Request):
    if _authority_config is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "AGENT_ROUTE_FORBIDDEN", "reason": "disabled"},
        )
    return await AgentRouteAuthority.for_bootstrap(_authority_config)(request)


async def _require_read_authority(request: Request):
    if _authority_config is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "AGENT_ROUTE_FORBIDDEN", "reason": "disabled"},
        )
    return await AgentRouteAuthority.for_read(_authority_config)(request)


def _success(data) -> dict:
    return {"status": "success", "data": data}


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, CatalogError):
        return HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.public_message},
        )
    if isinstance(exc, TrustError):
        return HTTPException(
            status_code=400,
            detail={
                "code": "MARKETPLACE_TRUST_FAILED",
                "message": "Marketplace package trust verification failed.",
            },
        )
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


@router.get("/catalog")
async def marketplace_catalog():
    try:
        return _success([entry.model_dump(mode="json") for entry in _catalog.list_entries()])
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/catalog/{plugin_id}")
async def marketplace_catalog_detail(plugin_id: str, version: str | None = None):
    try:
        return _success(_catalog.entry(plugin_id, version).model_dump(mode="json"))
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/catalog/refresh")
async def refresh_marketplace_catalog(
    request: RestartRequest,
    _authority=Depends(_require_mutation_authority),
):
    try:
        catalog = _catalog.refresh()
        return _success(
            {
                "publisherId": catalog.publisher_id,
                "generatedAt": catalog.generated_at.isoformat(),
                "entries": len(catalog.entries),
            }
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/plugins/{plugin_id}")
async def plugin_status(plugin_id: str):
    try:
        return _success(_manager.status(plugin_id).model_dump(mode="json"))
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/plugins/{plugin_id}/install")
async def install_plugin(
    plugin_id: str,
    request: InstallRequest,
    _authority=Depends(_require_mutation_authority),
):
    package = None
    try:
        entry = _catalog.entry(plugin_id, request.version)
        package = _catalog.acquire(entry)
        status = _manager.install(
            entry,
            package,
            approved_permissions=set(request.approved_permissions),
        )
        return _success(status.model_dump(mode="json"))
    except Exception as exc:
        raise _http_error(exc) from exc
    finally:
        if package is not None:
            package.unlink(missing_ok=True)


@router.post("/plugins/{plugin_id}/enable")
async def enable_plugin(
    plugin_id: str,
    request: EnableRequest,
    _authority=Depends(_require_mutation_authority),
):
    try:
        return _success(_manager.enable(plugin_id, set(request.permissions)).model_dump(mode="json"))
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/plugins/{plugin_id}/disable")
async def disable_plugin(
    plugin_id: str,
    request: RestartRequest,
    _authority=Depends(_require_mutation_authority),
):
    try:
        return _success(_manager.disable(plugin_id).model_dump(mode="json"))
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/plugins/{plugin_id}/rollback")
async def rollback_plugin(
    plugin_id: str,
    request: RollbackRequest,
    _authority=Depends(_require_mutation_authority),
):
    try:
        return _success(_manager.rollback(plugin_id, request.version).model_dump(mode="json"))
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/plugins/{plugin_id}/restart")
async def restart_plugin(
    plugin_id: str,
    request: RestartRequest,
    _authority=Depends(_require_mutation_authority),
):
    try:
        return _success(_manager.restart(plugin_id).model_dump(mode="json"))
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/plugins/{plugin_id}/uninstall")
async def uninstall_plugin(
    plugin_id: str,
    request: UninstallRequest,
    _authority=Depends(_require_mutation_authority),
):
    try:
        status = _manager.uninstall(plugin_id)
        return _success(status.model_dump(mode="json"))
    except Exception as exc:
        raise _http_error(exc) from exc


@host_router.get("/extensions")
async def enabled_extensions():
    if _authority_config is None:
        return _success({"extensions": []})
    extensions = _manager.enabled_extensions()
    for extension in extensions:
        extension["capabilities"] = _broker.capabilities_for(_manager, extension["pluginId"])
    return _success({"extensions": extensions})


@host_router.post("/bootstrap")
async def plugin_host_bootstrap(
    request: BootstrapRequest,
    _authority=Depends(_require_bootstrap_authority),
):
    assert _authority_config is not None
    return JSONResponse(
        _success(
            {
                "runToken": _authority_config.run_token.get_secret_value(),
                "header": "X-NextTrainer-Run-Token",
            }
        ),
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def _broker_error(request_id: str, exc: CapabilityBrokerError | None = None) -> JSONResponse:
    code = exc.code if exc is not None else "PLUGIN_CAPABILITY_FAILED"
    message = exc.public_message if exc is not None else "The plugin capability request failed."
    retryable = exc.retryable if exc is not None else False
    status_code = exc.status_code if exc is not None else 500
    return JSONResponse(
        {
            "ok": False,
            "requestId": request_id,
            "error": {"code": code, "message": message, "retryable": retryable},
        },
        status_code=status_code,
    )


def _confirmation_error(exc: ConfirmationError) -> JSONResponse:
    return JSONResponse(
        {
            "status": "error",
            "detail": {"code": exc.code, "message": exc.public_message},
        },
        status_code=exc.status_code,
    )


@host_router.get("/confirmations/pending")
async def pending_confirmations(_authority=Depends(_require_read_authority)):
    return _success({"confirmations": _confirmations.list_pending()})


@host_router.get("/confirmations/{ticket_id}")
async def confirmation_projection(ticket_id: str, _authority=Depends(_require_read_authority)):
    try:
        return _success(_confirmations.projection(ticket_id))
    except ConfirmationError as exc:
        return _confirmation_error(exc)


@host_router.post("/confirmations/{ticket_id}/resolve")
async def resolve_confirmation(
    ticket_id: str,
    request: ConfirmationResolutionRequest,
    _authority=Depends(_require_mutation_authority),
):
    try:
        return _success(_confirmations.resolve(ticket_id, request.decision))
    except ConfirmationError as exc:
        return _confirmation_error(exc)


@host_router.post("/extensions/{plugin_id}/requests")
async def plugin_capability_request(
    plugin_id: str,
    request: BrokerRequest,
    _authority=Depends(_require_mutation_authority),
):
    try:
        data = await _broker.request(_manager, plugin_id, request.request_id, request.method, request.params)
        return {"ok": True, "requestId": request.request_id, "data": data}
    except CapabilityBrokerError as exc:
        return _broker_error(request.request_id, exc)
    except Exception:
        return _broker_error(request.request_id)


@host_router.post("/extensions/{plugin_id}/streams")
async def plugin_capability_stream(
    plugin_id: str,
    request: BrokerRequest,
    _authority=Depends(_require_mutation_authority),
):
    try:
        stream = await _broker.stream(_manager, plugin_id, request.request_id, request.method, request.params)
    except CapabilityBrokerError as exc:
        return _broker_error(request.request_id, exc)
    except Exception:
        return _broker_error(request.request_id)

    async def events():
        yield "event: connected\ndata: " + json.dumps(
            {"ok": True, "requestId": request.request_id, "data": {"connected": True}},
            ensure_ascii=False,
        ) + "\n\n"
        try:
            async for event in stream:
                yield "event: data\ndata: " + json.dumps(
                    {"ok": True, "requestId": request.request_id, "data": event},
                    ensure_ascii=False,
                ) + "\n\n"
        except Exception:
            yield "event: error\ndata: " + json.dumps(
                {
                    "ok": False,
                    "requestId": request.request_id,
                    "error": {
                        "code": "PLUGIN_STREAM_FAILED",
                        "message": "The plugin event stream failed.",
                        "retryable": True,
                    },
                },
                ensure_ascii=False,
            ) + "\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@host_router.get("/ui/{plugin_id}/{version}/{asset_path:path}")
async def plugin_ui_artifact(plugin_id: str, version: str, asset_path: str):
    if _authority_config is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "AGENT_ROUTE_FORBIDDEN", "reason": "disabled"},
        )
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


__all__ = [
    "configure_capability_broker",
    "configure_confirmation_store",
    "configure_marketplace",
    "configure_marketplace_catalog",
    "configure_marketplace_authority",
    "get_confirmation_store",
    "host_router",
    "router",
]

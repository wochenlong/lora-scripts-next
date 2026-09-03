from __future__ import annotations

import asyncio
import logging
import os
import re
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
from .assets import AssetsUpdater
from .catalog import (
    CatalogError,
    FallbackCatalogSource,
    FileCatalogSource,
    HttpCatalogSource,
    HttpPackageAcquirer,
    LocalFirstPackageAcquirer,
    LocalPackageAcquirer,
    MarketplaceCatalogService,
    UnavailablePackageAcquirer,
)
from .operations import (
    InstallOperation,
    InstallOperationConflict,
    InstallOperationRegistry,
    OperationCancelled,
    STATE_RUNNING,
)
from .package import remove_tree
from .paths import MarketplacePaths
from .store import MarketplaceStore
from .trust import (
    _APPLIED_TRUST_FILE,
    TrustError,
    TrustStore,
    load_applied_trust,
    load_trust_root,
    verify_trust_update,
    write_applied_trust,
)


logger = logging.getLogger("mikazuki.plugin_marketplace.api")

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
    """Read the host version from the VERSION file next to the code root.

    ``utf-8-sig`` deliberately strips a UTF-8 BOM: Windows tooling (PowerShell
    5.1 ``Set-Content -Encoding UTF8``, Notepad "Save As UTF-8") writes BOMs by
    default, and a BOM-prefixed version string ("\\ufeff3.0.0-rc.4") used to
    blow up ``version_satisfies`` with a generic MARKETPLACE_TRUST_FAILED on
    every install (rc.4 live acceptance, V30).
    """
    version_file = Path(__file__).resolve().parents[2] / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8-sig").strip() or "0.0.0"
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


def _local_catalog_wiring(paths: MarketplacePaths) -> tuple[TrustStore, int, Any, Any]:
    """Catalog/trust wiring: explicit environment > bundled > fail-closed.

    1. Development: MIKAZUKI_MARKETPLACE_CATALOG / _TRUST (plus optional
       _PACKAGE_ROOT and _PACKAGE_MIRROR) environment variables. An explicit
       partial env (one of the two set) keeps the legacy fail-closed result.
       MIKAZUKI_MARKETPLACE_CATALOG_URL additionally pins a live HTTPS catalog
       (the release update channel); it wins while reachable and an explicit
       catalog file remains the offline fallback. A URL without a trust root
       fails closed like any other partial env.
    2. Bundled (release one-click package): the portable launcher runs the
       host with cwd = <root>/SD-Trainer, so a <cwd>/plugin-marketplace/
       directory containing catalog.json + trust.json (and optionally
       packages/*.zip) is picked up automatically — no environment needed.
    3. Neither: empty trust store and no catalog source, so every install
       fails closed.

    Package acquisition is local-first: catalog URLs mapped into the package
    root (env or bundled packages/) are copied from disk; anything else is
    downloaded over HTTP, optionally rewritten onto the loopback
    MIKAZUKI_MARKETPLACE_PACKAGE_MIRROR (release dry-run against a local
    file server). Integrity always comes from the catalog-pinned size+sha256.
    """
    env_catalog = os.environ.get("MIKAZUKI_MARKETPLACE_CATALOG", "").strip()
    env_trust = os.environ.get("MIKAZUKI_MARKETPLACE_TRUST", "").strip()
    env_catalog_url = os.environ.get("MIKAZUKI_MARKETPLACE_CATALOG_URL", "").strip()
    package_root = os.environ.get("MIKAZUKI_MARKETPLACE_PACKAGE_ROOT", "").strip()
    mirror = os.environ.get("MIKAZUKI_MARKETPLACE_PACKAGE_MIRROR", "").strip() or None
    catalog_source: Any = None
    if env_catalog or env_trust or env_catalog_url:
        # Explicit tier: the trust root is mandatory (partial env fails closed),
        # and at least one catalog source (live URL and/or file) must resolve.
        if not env_trust:
            return TrustStore({}), 0, None, None
        try:
            if env_catalog_url:
                catalog_source = HttpCatalogSource(env_catalog_url)
            if env_catalog:
                file_source = FileCatalogSource(Path(env_catalog))
                catalog_source = (
                    file_source
                    if catalog_source is None
                    else FallbackCatalogSource(catalog_source, file_source)
                )
        except ValueError:
            return TrustStore({}), 0, None, None
        if catalog_source is None:
            return TrustStore({}), 0, None, None
        trust_path = env_trust
    else:
        bundled = Path.cwd() / "plugin-marketplace"
        catalog_candidate = bundled / "catalog.json"
        trust_candidate = bundled / "trust.json"
        if not (catalog_candidate.is_file() and trust_candidate.is_file()):
            return TrustStore({}), 0, None, None
        trust_path = str(trust_candidate)
        catalog_source = FileCatalogSource(catalog_candidate)
        if not package_root and (bundled / "packages").is_dir():
            package_root = str(bundled / "packages")
    trust = load_trust_root(Path(trust_path))
    acquirer: Any = UnavailablePackageAcquirer()
    if package_root:
        sources: dict[str, Path] = {}
        root_dir = Path(package_root).resolve()
        if root_dir.is_dir():
            # Convention: every *.zip in the package root is addressable as
            # https://plugins.next-trainer.local/packages/<file name>.
            for member in sorted(root_dir.iterdir()):
                if member.is_file() and member.suffix.casefold() == ".zip":
                    sources[f"https://plugins.next-trainer.local/packages/{member.name}"] = member
        acquirer = LocalFirstPackageAcquirer(LocalPackageAcquirer(sources), HttpPackageAcquirer(mirror))
    elif env_catalog_url:
        # A LIVE HTTPS channel (MIKAZUKI_MARKETPLACE_CATALOG_URL) is installable
        # BY DESIGN: the entry pins the package's https URL + size + sha256, and
        # the package is served from the same release as the catalog, so HTTP
        # acquisition is implicitly available. Without this, uninstall-then-reinstall
        # failed with MARKETPLACE_PACKAGE_ACQUISITION_UNAVAILABLE while the cached
        # catalog kept rendering an installable listing ("clicked install, nothing
        # happens"). A FILE catalog (env_catalog) stays fail-closed without a
        # package root: the portable one-click bundle must remain self-contained
        # and never reach the network silently.
        acquirer = HttpPackageAcquirer(mirror)
    # P1-5: an APPLIED trust update (rotation/revocation from a governed
    # release, chain-verified at apply time) takes precedence over the
    # shipped root. A corrupted applied file falls back to the shipped root
    # — the host is never bricked by its own trust state.
    trust_seq = 0
    applied_file = paths.root / _APPLIED_TRUST_FILE
    if applied_file.is_file():
        try:
            trust, trust_seq = load_applied_trust(applied_file)
            logger.info(
                "marketplace: effective trust = applied update (seq %d, fingerprint %s)",
                trust_seq,
                trust.fingerprint(),
            )
        except TrustError as exc:
            logger.warning("marketplace: applied trust root is invalid (%s); using the shipped root", exc)
    return trust, trust_seq, catalog_source, acquirer


def _marketplace_paths() -> MarketplacePaths:
    """The host-writable marketplace root (env override or <cwd>/.runtime).

    Resolved before catalog wiring: the applied-trust file (P1-5) lives in
    this root, so the wiring must know it.
    """
    configured = os.environ.get("MIKAZUKI_PLUGIN_MARKETPLACE_ROOT", "").strip()
    root = Path(configured).resolve() if configured else (Path.cwd() / ".runtime" / "plugin-marketplace").resolve()
    return MarketplacePaths(root)


def _default_manager() -> MarketplaceManager:
    paths = _marketplace_paths()
    port = os.environ.get("MIKAZUKI_PORT", "28000").strip()
    # Production trust roots are release-governed.  An empty root keeps status,
    # uninstall and core startup available while making every install fail closed.
    return MarketplaceManager(
        paths=paths,
        store=MarketplaceStore(paths.registry_file),
        trust=_trust,
        host_version=_host_version(),
        platform=_platform_name(),
        runtime=ExecutablePluginRuntime(
            # The sidecar appends /internal/agent-tools/... itself; the app
            # mounts the agent-tools router under the /api prefix.
            host_tool_base_url=f"http://127.0.0.1:{port}/api",
        ),
    )


_trust, _trust_seq, _catalog_source, _catalog_acquirer = _local_catalog_wiring(_marketplace_paths())
_manager = _default_manager()
_catalog = MarketplaceCatalogService(
    paths=_manager.paths,
    trust=_trust,
    source=_catalog_source,
    acquirer=_catalog_acquirer,
)


def _apply_pending_trust_update() -> bool:
    """P1-5: apply a pending ``trust-update.json`` from the marketplace root.

    Chain of trust: the update is signed by a key the CURRENT effective
    trust already trusts (never by a key the update itself introduces), and
    ``seq`` must strictly advance past the applied seq — replays and
    rollbacks are rejected. On success the applied root is persisted
    (restart-proof), the update file is archived for audit, and the
    manager/catalog trust references are swapped so ALL subsequent
    catalog/update verification uses the new trust. On ANY failure the
    current trust stays in force (the host is never bricked) and the event
    is logged.
    """
    global _trust, _trust_seq
    paths = _manager.paths
    update_file = paths.root / "trust-update.json"
    try:
        if not update_file.is_file():
            return False
        payload = update_file.read_bytes()
    except OSError as exc:
        logger.warning("trust update unreadable, keeping current trust: %s", exc)
        return False
    try:
        candidate, seq = verify_trust_update(_trust, _trust_seq, payload)
    except TrustError as exc:
        logger.warning("trust update rejected, keeping current trust: %s", exc)
        return False
    try:
        update = json.loads(payload)
        source = {
            "signingKeyId": update.get("signingKeyId"),
            "signature": update.get("signature"),
            "origin": "trust-update.json",
        }
        write_applied_trust(paths.root / _APPLIED_TRUST_FILE, candidate, seq, source=source)
        update_file.replace(paths.root / f"trust-update.json.applied.{seq}")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.error("trust update persistence failed, keeping current trust: %s", exc)
        return False
    _trust = candidate
    _trust_seq = seq
    _manager.trust = _trust
    _catalog.trust = _trust
    logger.info("trust update applied: seq %d, fingerprint %s", seq, _trust.fingerprint())
    return True


def startup_apply_trust_update() -> bool:
    """P1-5 startup hook (best-effort): a broken trust update must never
    block application startup — it is logged and the shipped trust stays."""
    try:
        return _apply_pending_trust_update()
    except Exception:  # noqa: BLE001 — never block startup on cache/trust hygiene
        return False


def startup_resume_enabled() -> list[str]:
    """Re-activate persisted-enabled plugins on application startup.

    Plugin runtimes are child processes of the host process, so a host restart
    ends them while the registry still records `enabled`; without this the
    floating panel shows a plugin the user never disabled as "not ready" until
    they press restart. Fire-and-forget from the app lifespan: best-effort,
    returns the resumed ids, and NEVER raises so a broken plugin cannot block
    application startup.
    """
    try:
        return _manager.resume_enabled()
    except Exception:
        return []


def _build_assets_updater() -> AssetsUpdater:
    """Managed business-data channel wiring (F3-3).

    NEXT_TRAINER_ASSETS_INDEX_URL pins the signed assets index (env mirror of
    the release channel; NEXT_TRAINER_ASSETS_MIRROR rewrites its zip URL onto
    a loopback file server for dry-runs). A malformed URL disables ONLY the
    assets channel — marketplace and training stay fully functional.
    """
    try:
        return AssetsUpdater(
            _manager.paths,
            _trust,
            index_url=os.environ.get("NEXT_TRAINER_ASSETS_INDEX_URL", "").strip() or None,
            mirror_base_url=os.environ.get("NEXT_TRAINER_ASSETS_MIRROR", "").strip() or None,
        )
    except ValueError:
        return AssetsUpdater(_manager.paths, _trust)


_assets = _build_assets_updater()
_confirmations = ConfirmationTicketStore()
configure_agent_tool_service(_confirmations)


def _install_pipeline(op: InstallOperation, entry: MarketplaceEntry, approved_permissions: set[str]) -> None:
    """Background install pipeline; runs off the event loop in a worker thread.

    Must finish the operation on every path: success via op.finish_success,
    or by raising (OperationCancelled / any exception is classified by the
    registry worker).
    """
    def on_progress(current: int, total: int) -> None:
        if op.cancel_requested:
            raise OperationCancelled()
        op.report_progress("acquiring", current, total)

    def is_cancelled() -> bool:
        return op.cancel_requested

    def on_phase(phase: str) -> None:
        if not op.cancel_requested:
            op.report_phase(phase)

    op.report_phase("acquiring")
    # acquire() lands the zip in the PERSISTENT package cache (V30): the file
    # is deliberately NOT unlinked here. Cancelling (or failing) after the
    # download keeps the verified zip on disk, so the next install of the same
    # pinned package skips the download entirely.
    package = _catalog.acquire(entry, _platform_name(), on_progress=on_progress, is_cancelled=is_cancelled)
    # Cancellation is honored while acquiring. manager.install() runs under the
    # plugin lock and deliberately swallows every on_phase exception ("progress
    # must never break the install"), so once install() returns the plugin IS
    # committed — reporting "cancelled" there would be false (Copilot C-9).
    status = _manager.install(entry, package, approved_permissions=approved_permissions, on_phase=on_phase)
    _prune_package_cache_best_effort({package})
    op.finish_success(status.model_dump(mode="json"))


def _prune_package_cache_best_effort(keep: set[Path] = frozenset()) -> None:
    """P1-4 trigger: global package-cache LRU after install/uninstall/refresh.

    Protects every installed plugin's ACTIVE-version quarantine zip (the
    rollback/reinstall path reuses it) plus the caller's keep set (the
    just-acquired package). Never raises — cache hygiene must not break the
    operation it follows (the prune method itself is best-effort too).
    """
    try:
        protected: set[Path] = set(keep)
        plugins = (_manager.store.snapshot() or {}).get("plugins") or {}
        for plugin_id, record in plugins.items():
            active = (record or {}).get("active_version")
            if active:
                try:
                    protected.add(_manager.paths.quarantine_package(plugin_id, active))
                except Exception:  # noqa: BLE001 — an odd id must not kill the sweep
                    continue
        _catalog.prune_global_package_cache(protected)
    except Exception:  # noqa: BLE001
        pass


_install_operations = InstallOperationRegistry(_install_pipeline)


def configure_install_operations(registry: InstallOperationRegistry) -> None:
    global _install_operations
    _install_operations = registry


def _cleanup_stale_install_artifacts(paths: MarketplacePaths) -> None:
    """Remove incomplete download temps / staging dirs left by a killed install.

    Verified package zips in the quarantine cache are INTENTIONALLY KEPT (V30):
    they are the persistent download cache that makes a cancelled or failed
    install free to retry. Only ``*.part`` temps (aborted mid-download) and
    stale staging trees (manager.install cleans its own in a finally block)
    are removed at startup.
    """
    quarantine = paths.quarantine_root
    if quarantine.is_dir():
        for plugin_dir in quarantine.iterdir():
            if plugin_dir.is_dir():
                for member in plugin_dir.iterdir():
                    if member.is_file() and member.name.endswith(".part"):
                        member.unlink(missing_ok=True)
    staging = paths.staging_root
    if staging.is_dir():
        for plugin_dir in staging.iterdir():
            if plugin_dir.is_dir():
                remove_tree(plugin_dir, ignore_errors=True)


_cleanup_stale_install_artifacts(_manager.paths)


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
    """Swap the trusted confirmation store and keep the tool service in sync.

    The Host Tool gateway and the confirmation REST routes must observe the
    same live store; reconfiguring only one side would silently split ticket
    creation from ticket resolution across two stores.
    """
    global _confirmations
    _confirmations = store
    configure_agent_tool_service(store)


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


def _compare_marketplace_versions(candidate: str, current: str) -> int | None:
    """Order two marketplace versions for update detection.

    Returns >0 when ``candidate`` is newer, <0 when older, 0 when equal, and
    None when either version cannot be parsed (callers must treat that as
    "unknown", never as an update). Numeric parts compare numerically; a
    pre-release suffix (e.g. ``-rc.1``) orders BEFORE the corresponding
    release, per semver.
    """
    def _parts(version: str) -> tuple[tuple[int, ...], str] | None:
        text = version.strip()
        match = re.match(r"^(\d+(?:\.\d+)*)(.*)$", text)
        if not match:
            return None
        numbers = tuple(int(part) for part in match.group(1).split("."))
        return numbers, match.group(2).strip()

    left = _parts(candidate)
    right = _parts(current)
    if left is None or right is None:
        return None
    (left_numbers, left_suffix), (right_numbers, right_suffix) = left, right
    padded_left = left_numbers + (0,) * (len(right_numbers) - len(left_numbers))
    padded_right = right_numbers + (0,) * (len(left_numbers) - len(right_numbers))
    if padded_left != padded_right:
        return 1 if padded_left > padded_right else -1
    # Equal numeric core: a pre-release sorts before the release.
    if left_suffix == right_suffix:
        return 0
    if not left_suffix:
        return 1
    if not right_suffix:
        return -1
    return 1 if left_suffix > right_suffix else -1


def _update_info(status) -> dict:
    """Honest update availability for an installed plugin (P0-3).

    Every field is present on every response so clients can rely on the keys:
    no catalog entry (cold/offline host) or an unparseable version keeps the
    fields at their "unknown" defaults instead of inventing an update.
    """
    info = {
        "update_available": False,
        "latest_version": None,
        "update_size_bytes": None,
        "update_permissions_added": None,
        "update_permissions_removed": None,
    }
    if not status.active_version:
        return info
    try:
        entry = _catalog.entry(status.id)
    except Exception:  # noqa: BLE001 — a cold/offline catalog is an "unknown"
        return info
    comparison = _compare_marketplace_versions(entry.latest_version, status.active_version)
    if comparison is None or comparison <= 0:
        return info
    # Permission diff is VERSION to VERSION (task book P0-3): the newest
    # summary against the currently active version's manifest, so the update
    # confirmation can demand re-approval of every changed grant. Fall back
    # to the granted set when the active manifest is missing from the record.
    record = _manager.store.get_plugin(status.id) or {}
    active_manifest = ((record.get("versions") or {}).get(status.active_version) or {}).get("manifest") or {}
    current_permissions = set(active_manifest.get("permissions") or record.get("granted_permissions") or ())
    new_permissions = set(entry.permissions_summary)
    info["update_available"] = True
    info["latest_version"] = entry.latest_version
    info["update_size_bytes"] = entry.package_size
    info["update_permissions_added"] = sorted(new_permissions - current_permissions)
    info["update_permissions_removed"] = sorted(current_permissions - new_permissions)
    return info


def _status_payload(status) -> dict:
    """Plugin status JSON plus the live install operation (if any).

    The marketplace page can be left and re-entered (or the whole host UI
    reloaded by the post-install refresh) while an install keeps running in
    the background; surfacing the operation here is what lets the page
    re-attach its progress UI instead of going blind. Also carries the
    update-availability fields (P0-3) computed against the latest catalog.
    """
    payload = status.model_dump(mode="json")
    operation = _install_operations.active(status.id)
    payload["activeOperation"] = operation.snapshot() if operation else None
    payload.update(_update_info(status))
    return payload


@router.get("/plugins")
async def list_plugins():
    payloads = [_status_payload(status) for status in _manager.list_statuses()]
    # A first-time install has no registry entry yet, so list_statuses omits
    # the plugin entirely — but the running operation must still surface so a
    # page that re-attaches (navigation / host reload) can find it here too.
    listed = {payload["id"] for payload in payloads}
    for plugin_id in _install_operations.active_plugin_ids():
        if plugin_id not in listed:
            try:
                payloads.append(_status_payload(_manager.status(plugin_id)))
            except Exception:  # noqa: BLE001 — best-effort; skip unresolvable ids
                continue
    return _success(payloads)


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


@router.get("/trust")
async def trust_status():
    """P1-5: the effective trust root state (fingerprint + seq + key ids).

    UI display surface for "which trust verifies the marketplace right now"
    — after a rotation the fingerprint changes and the seq advances; the
    fingerprint is a one-way digest, never key material.
    """
    return _success(
        {
            "fingerprint": _trust.fingerprint(),
            "seq": _trust_seq,
            "source": "applied" if _trust_seq > 0 else "shipped",
            "keyIds": _trust.key_ids,
            "revokedKeyIds": _trust.revoked_key_ids,
        }
    )


@router.post("/catalog/refresh")
async def refresh_marketplace_catalog(
    request: RestartRequest,
    _authority=Depends(_require_mutation_authority),
):
    try:
        # P1-5: a trust update may have landed (release sync) while the host
        # was running — apply it (chain-verified, best-effort) so the refresh
        # below verifies the catalog with the NEW effective trust.
        _apply_pending_trust_update()
        catalog = _catalog.refresh()
        _prune_package_cache_best_effort()
        return _success(
            {
                "publisherId": catalog.publisher_id,
                "generatedAt": catalog.generated_at.isoformat(),
                "entries": len(catalog.entries),
                "trustSeq": _trust_seq,
                "trustFingerprint": _trust.fingerprint(),
                "trustSource": "applied" if _trust_seq > 0 else "shipped",
            }
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/plugins/{plugin_id}")
async def plugin_status(plugin_id: str):
    try:
        return _success(_status_payload(_manager.status(plugin_id)))
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/plugins/{plugin_id}/install")
async def install_plugin(
    plugin_id: str,
    request: InstallRequest,
    _authority=Depends(_require_mutation_authority),
):
    """Start an install operation and return 202 with its id.

    The install itself (package acquisition + extraction + health check +
    commit) runs in a background worker; clients follow progress via
    GET .../operations/{id} (polling) or GET .../operations/{id}/stream (SSE)
    and may abort with DELETE .../operations/{id}.
    """
    try:
        entry = _catalog.entry(plugin_id, request.version)
        try:
            operation = _install_operations.start(plugin_id, entry, set(request.approved_permissions))
        except InstallOperationConflict:
            # A repeated install click (or a client that navigated away and
            # back) ATTACHES to the in-flight work instead of failing: the
            # operation is plugin-scoped and already carries the same catalog
            # entry, so returning the running snapshot is both idempotent and
            # what the user means by pressing install again. A running
            # install of a DIFFERENT version stays a conflict.
            existing = _install_operations.active(plugin_id)
            if existing is None or existing.version != entry.latest_version:
                raise
            operation = existing
    except InstallOperationConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MARKETPLACE_INSTALL_IN_PROGRESS",
                "message": "An install is already running for this plugin.",
            },
        ) from exc
    except Exception as exc:
        raise _http_error(exc) from exc
    return JSONResponse(status_code=202, content=_success(operation.snapshot()))


@router.get("/plugins/{plugin_id}/operations/{operation_id}")
async def install_operation_status(plugin_id: str, operation_id: str):
    operation = _install_operations.get(plugin_id, operation_id)
    if operation is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "MARKETPLACE_OPERATION_NOT_FOUND",
                "message": "The install operation was not found.",
            },
        )
    return _success(operation.snapshot())


@router.delete("/plugins/{plugin_id}/operations/{operation_id}")
async def cancel_install_operation(
    plugin_id: str,
    operation_id: str,
    _authority=Depends(_require_mutation_authority),
):
    # Mutation authority requires a JSON body (content-type application/json);
    # clients send an empty object.
    operation = _install_operations.get(plugin_id, operation_id)
    if operation is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "MARKETPLACE_OPERATION_NOT_FOUND",
                "message": "The install operation was not found.",
            },
        )
    if not operation.request_cancel():
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MARKETPLACE_OPERATION_NOT_CANCELLABLE",
                "message": "The install operation has already finished.",
            },
        )
    return _success(operation.snapshot())


@router.get("/plugins/{plugin_id}/operations/{operation_id}/stream")
async def install_operation_stream(plugin_id: str, operation_id: str):
    operation = _install_operations.get(plugin_id, operation_id)
    if operation is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "MARKETPLACE_OPERATION_NOT_FOUND",
                "message": "The install operation was not found.",
            },
        )

    async def events():
        yield 'event: connected\ndata: {"status": "success", "data": {"connected": true}}\n\n'
        last_payload: str | None = None
        while True:
            snapshot = operation.snapshot()
            payload = json.dumps({"status": "success", "data": snapshot}, ensure_ascii=False)
            if payload != last_payload:
                event = "progress" if snapshot["state"] == STATE_RUNNING else "done"
                yield f"event: {event}\ndata: {payload}\n\n"
                last_payload = payload
            if snapshot["state"] != STATE_RUNNING:
                return
            await asyncio.sleep(0.35)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


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


@router.get("/plugins/{plugin_id}/assets/status")
async def assets_status(plugin_id: str):
    """Managed business-data channel state; never touches the network."""
    try:
        status = _manager.status(plugin_id)
        if status.state == "not_installed":
            raise CatalogError(
                "MARKETPLACE_PLUGIN_MISSING",
                "The plugin is not installed.",
                status_code=404,
            )
        return _success(_assets.status(plugin_id))
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/plugins/{plugin_id}/assets/update")
async def assets_update(
    plugin_id: str,
    request: RestartRequest,
    _authority=Depends(_require_mutation_authority),
):
    """Pull the signed assets release into the managed namespaces (F3-3).

    Updates only knowledge/, templates/ and pi-agent skills/ trees tracked by
    the managed manifest; user files are sovereign (see assets.AssetsUpdater).
    Any failure is reported and leaves both the tree and the manifest whole.
    """
    try:
        status = _manager.status(plugin_id)
        if status.state == "not_installed":
            raise CatalogError(
                "MARKETPLACE_PLUGIN_MISSING",
                "The plugin is not installed.",
                status_code=404,
            )
        return _success(_assets.update(plugin_id))
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
        _prune_package_cache_best_effort()
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

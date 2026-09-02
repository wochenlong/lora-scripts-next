from __future__ import annotations

import base64
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from .artifacts import TrainingConfigArtifactService
from .errors import AgentDomainError
from .workspace import AgentWorkspace

router = APIRouter(prefix="/agent-workspace", tags=["agent-workspace"])
_workspaces: dict[str, AgentWorkspace] = {}
_artifact_services: dict[str, TrainingConfigArtifactService] = {}


def _workspace_root() -> Path:
    configured = os.environ.get("MIKAZUKI_AGENT_WORKSPACE_ROOT", "").strip()
    return Path(configured).absolute() if configured else Path.cwd() / ".runtime" / "agent-workspaces"


def _error(exc: AgentDomainError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.as_dict())


def _get_workspace(session_id: str) -> AgentWorkspace:
    workspace = _workspaces.get(session_id)
    if workspace is None:
        raise AgentDomainError("WORKSPACE_NOT_FOUND", "Agent workspace was not found.", status_code=404)
    return workspace


def get_workspace(session_id: str) -> AgentWorkspace:
    """Return the host-owned workspace used by both HTTP and Sidecar Tools."""
    return _get_workspace(session_id)


def ensure_workspace(session_id: str, *, purpose: str = "agent") -> AgentWorkspace:
    """Create a session workspace lazily for a Sidecar Tool call.

    The session id is validated by ``AgentWorkspace`` before it becomes a
    filesystem component.  This keeps Tool calls useful immediately after a
    Pi session is created while retaining the same workspace boundary as the
    explicit REST API.
    """
    workspace = _workspaces.get(session_id)
    if workspace is None:
        workspace = AgentWorkspace(_workspace_root(), session_id=session_id, purpose=purpose)
        workspace.create()
        _workspaces[session_id] = workspace
    return workspace


def get_artifact_service(session_id: str) -> TrainingConfigArtifactService:
    return _service(session_id)


@router.post("/workspaces")
async def create_workspace(request: Request):
    try:
        payload = json.loads(await request.body() or b"{}")
        session_id = payload.get("sessionId")
        workspace = AgentWorkspace(
            _workspace_root(),
            session_id=session_id,
            purpose=str(payload.get("purpose") or "training-config"),
            workspace_class=payload.get("workspaceClass"),
            allowed_extensions=payload.get("allowedExtensions") or (".toml", ".json", ".txt", ".md"),
            source_revision=payload.get("sourceRevision"),
            source_snapshot_hash=payload.get("sourceSnapshotHash"),
        )
        workspace.create()
        _workspaces[workspace.manifest.session_id] = workspace
        _artifact_services.pop(workspace.manifest.session_id, None)
        return {"status": "success", "data": workspace.manifest.as_dict()}
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail={"code": "WORKSPACE_INVALID", "message": "Workspace request is invalid."}) from exc
    except AgentDomainError as exc:
        raise _error(exc) from None


@router.get("/workspaces/{session_id}/manifest")
async def workspace_manifest(session_id: str):
    try:
        return {"status": "success", "data": _get_workspace(session_id).manifest.as_dict()}
    except AgentDomainError as exc:
        raise _error(exc) from None


@router.post("/workspaces/{session_id}/files/read")
async def workspace_read(session_id: str, request: Request):
    try:
        workspace = _get_workspace(session_id)
        payload = json.loads(await request.body() or b"{}")
        path = payload.get("path")
        data = workspace.read_bytes(path, writable=bool(payload.get("writable", True)))
        return {"status": "success", "data": {"path": path, "encoding": "base64", "content": base64.b64encode(data).decode("ascii"), "contentHash": workspace.file_hash(path, writable=bool(payload.get("writable", True)))}}
    except (json.JSONDecodeError, TypeError, ValueError):
        raise HTTPException(status_code=400, detail={"code": "WORKSPACE_REQUEST_INVALID", "message": "Workspace request is invalid."}) from None
    except AgentDomainError as exc:
        raise _error(exc) from None


@router.post("/workspaces/{session_id}/files/write")
async def workspace_write(session_id: str, request: Request):
    try:
        workspace = _get_workspace(session_id)
        payload = json.loads(await request.body() or b"{}")
        path = payload.get("path")
        if payload.get("encoding", "utf-8") == "base64":
            content = base64.b64decode(payload.get("content", ""), validate=True)
        else:
            content = str(payload.get("content", "")).encode("utf-8")
        result = workspace.write_bytes(path, content, overwrite=bool(payload.get("overwrite", True)))
        return {"status": "success", "data": result}
    except (json.JSONDecodeError, TypeError, ValueError, base64.binascii.Error):
        raise HTTPException(status_code=400, detail={"code": "WORKSPACE_REQUEST_INVALID", "message": "Workspace request is invalid."}) from None
    except AgentDomainError as exc:
        raise _error(exc) from None


def _service(session_id: str) -> TrainingConfigArtifactService:
    service = _artifact_services.get(session_id)
    if service is None:
        service = TrainingConfigArtifactService(_get_workspace(session_id))
        _artifact_services[session_id] = service
    return service


@router.post("/workspaces/{session_id}/training-config/get-template")
async def training_config_template(session_id: str, request: Request):
    try:
        payload = json.loads(await request.body() or b"{}")
        return {"status": "success", "data": _service(session_id).get_template(payload.get("pageTrainType") or payload.get("page_train_type"))}
    except (json.JSONDecodeError, TypeError, ValueError):
        raise HTTPException(status_code=400, detail={"code": "CONFIG_REQUEST_INVALID", "message": "Training configuration request is invalid."}) from None
    except AgentDomainError as exc:
        raise _error(exc) from None


@router.post("/workspaces/{session_id}/training-config/validate-draft")
async def training_config_validate(session_id: str, request: Request):
    try:
        payload = json.loads(await request.body() or b"{}")
        service = _service(session_id)
        data = service.validate_draft(payload.get("path"), page_train_type=payload.get("pageTrainType") or payload.get("page_train_type"), baseline_artifact=payload.get("baselinePath"), metadata=payload.get("metadata"))
        return {"status": "success", "data": data}
    except (json.JSONDecodeError, TypeError, ValueError):
        raise HTTPException(status_code=400, detail={"code": "CONFIG_REQUEST_INVALID", "message": "Training configuration request is invalid."}) from None
    except AgentDomainError as exc:
        raise _error(exc) from None


@router.post("/workspaces/{session_id}/training-config/commit-draft")
async def training_config_commit(session_id: str, request: Request):
    # The confirmation ticket is host-owned and never caller-supplied: the
    # caller names a ticket id and the host resolves, atomically claims and
    # consumes the real server-side ticket. Inline ticket objects are rejected
    # outright so a caller can never forge {"state": "approved"}; possession of
    # an unguessable, user-approved ticket id is the authorization.
    raw = await request.body() or b"{}"
    if b'"confirmationTicket"' in raw:
        raise HTTPException(status_code=400, detail={"code": "CONFIG_TICKET_INLINE_FORBIDDEN", "message": "Commit requires a host-issued confirmationTicketId; inline confirmation ticket objects are not accepted."})
    try:
        payload = json.loads(raw or b"{}")
    except (json.JSONDecodeError, TypeError, ValueError):
        raise HTTPException(status_code=400, detail={"code": "CONFIG_REQUEST_INVALID", "message": "Training configuration request is invalid."}) from None
    ticket_id = payload.get("confirmationTicketId")
    if not isinstance(ticket_id, str) or not ticket_id.strip():
        raise HTTPException(status_code=400, detail={"code": "CONFIG_CONFIRMATION_REQUIRED", "message": "A host-issued confirmationTicketId is required to commit a validated draft."})
    from mikazuki.plugin_host.confirmation import ConfirmationError
    from mikazuki.plugin_marketplace.api import get_confirmation_store

    confirmations = get_confirmation_store()
    try:
        # action-bind the claim: only a ticket the user approved FOR this commit
        # may commit; a ticket approved for another write action is rejected.
        projection = confirmations.claim(ticket_id, action="training_config_commit")
    except ConfirmationError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.public_message}) from None
    try:
        # The canonical output directory is host-owned. A plugin may approve a
        # validated draft but cannot choose an arbitrary filesystem destination.
        data = _service(session_id).commit_draft(payload.get("validationHash") or payload.get("validation_hash"), confirmation_ticket=projection, source_revision=payload.get("sourceRevision"))
    except AgentDomainError as exc:
        confirmations.release(ticket_id)
        raise _error(exc) from None
    except (json.JSONDecodeError, TypeError, ValueError):
        confirmations.release(ticket_id)
        raise HTTPException(status_code=400, detail={"code": "CONFIG_REQUEST_INVALID", "message": "Training configuration request is invalid."}) from None
    confirmations.consume(ticket_id)
    return {"status": "success", "data": data}


__all__ = ["router", "ensure_workspace", "get_artifact_service", "get_workspace"]

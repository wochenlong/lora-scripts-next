from __future__ import annotations

"""Host-owned custom Tools exposed to the optional Pi Agent sidecar.

The module is deliberately a thin adapter.  Domain rules stay in the
workspace, dataset, skills and metrics packages; this layer supplies the
session/token boundary, stable Tool schemas and confirmation handling.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from fastapi import APIRouter, HTTPException, Request

from mikazuki.agent_dataset import (
    ActiveModelCapability,
    CaptionChangeSet,
    CaptionOverlay,
    DatasetReviewError,
    inventory_dataset,
    review_images,
    select_review_sample,
)
from mikazuki.agent_metrics import (
    FixedComparisonProtocol,
    analyze_curve,
    compare_artifacts,
    recommend_artifacts,
)
from mikazuki.agent_skills import CivitaiClient, CivitaiQuery, KnowledgeStore
from mikazuki.agent_skills.cohort import build_cohort_report
from mikazuki.agent_skills.models import KnowledgeDocument, SourceRef
from mikazuki.agent_workspace import get_artifact_service, ensure_workspace
from mikazuki.agent_workspace import redact
from .confirmation import ConfirmationError, ConfirmationTicketStore


router = APIRouter(prefix="/internal/agent-tools", tags=["agent-tools"])


@dataclass(frozen=True)
class _Tool:
    name: str
    label: str
    description: str
    permission: str
    side_effect: str
    parameters: dict[str, Any]
    handler: Callable[[str, str, dict[str, Any]], Any]


def _object(properties: dict[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


def _str(description: str = "") -> dict[str, Any]:
    value: dict[str, Any] = {"type": "string", "minLength": 1}
    if description:
        value["description"] = description
    return value


def _tool_error(exc: Exception) -> HTTPException:
    code = getattr(exc, "code", "TOOL_FAILED")
    message = getattr(exc, "public_message", None) or getattr(exc, "message", None) or "The Host Tool request failed."
    status = int(getattr(exc, "status_code", 400))
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _as_dict(value: Any) -> Any:
    if hasattr(value, "as_dict"):
        return value.as_dict()
    if isinstance(value, Mapping):
        return {str(key): _as_dict(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_as_dict(child) for child in value]
    return value


class AgentToolService:
    """Session-scoped adapter and confirmation-aware dispatcher."""

    def __init__(self, confirmations: ConfirmationTicketStore) -> None:
        self.confirmations = confirmations
        self._overlays: dict[tuple[str, str], CaptionOverlay] = {}
        self._change_sets: dict[tuple[str, str], CaptionChangeSet] = {}
        self._knowledge: dict[str, KnowledgeStore] = {}

    def definitions(self, granted_permissions: frozenset[str]) -> list[dict[str, Any]]:
        """Least-privilege catalog: only tools whose permission the plugin was granted."""
        return [
            {"name": tool.name, "label": tool.label, "description": tool.description, "parameters": tool.parameters}
            for tool in sorted(self._tools().values(), key=lambda item: item.name)
            if tool.permission in granted_permissions
        ]

    async def invoke(self, plugin_id: str, session_id: str, tool_call_id: str, name: str, params: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(tool_call_id, str) or not tool_call_id.strip():
            raise HTTPException(status_code=400, detail={"code": "TOOL_CALL_ID_REQUIRED", "message": "A Tool call id is required."})
        tool = self._tools().get(name)
        if tool is None:
            raise HTTPException(status_code=404, detail={"code": "TOOL_NOT_FOUND", "message": "The requested Host Tool is unavailable."})
        if tool.permission not in _granted_permissions(plugin_id):
            raise HTTPException(
                status_code=403,
                detail={"code": "TOOL_PERMISSION_DENIED", "message": "The plugin is not authorized for this Host Tool."},
            )
        if not isinstance(params, dict):
            raise HTTPException(status_code=400, detail={"code": "TOOL_PARAMS_INVALID", "message": "Tool arguments must be an object."})
        ticket_id = params.get("confirmationTicketId")
        if tool.side_effect == "write":
            approved = None
            if isinstance(ticket_id, str) and ticket_id:
                try:
                    projection = self.confirmations.projection(ticket_id)
                    if projection.get("pluginId") != plugin_id or projection.get("toolCallId") != tool_call_id:
                        raise HTTPException(status_code=409, detail={"code": "CONFIRMATION_MISMATCH", "message": "The confirmation ticket is not bound to this Tool call."})
                    approved = projection if projection.get("state") == "approved" else None
                except ConfirmationError as exc:
                    raise _tool_error(exc) from None
            if approved is None:
                ticket = self.confirmations.create_pending(
                    plugin_id=plugin_id,
                    tool_call_id=tool_call_id,
                    permission=tool.permission,
                    action=tool.name,
                    title=tool.label,
                    summary=tool.description,
                    details=redact({key: value for key, value in params.items() if key != "confirmationTicketId"}),
                )
                return {"state": "confirmation_required", "ticket": ticket.projection(), "tool": tool.name}
        clean_params = dict(params)
        try:
            value = tool.handler(session_id, tool_call_id, clean_params)
            if asyncio.iscoroutine(value):
                value = await value
            return redact(_as_dict(value))
        except HTTPException:
            raise
        except Exception as exc:
            raise _tool_error(exc) from None

    def _tools(self) -> dict[str, _Tool]:
        return {
            "training_config_template": _Tool(
                "training_config_template", "Training config template", "Get the canonical TOML/JSON training config contract.", "training-config", "read",
                _object({"pageTrainType": _str()}, ("pageTrainType",)), self._config_template,
            ),
            "training_config_validate": _Tool(
                "training_config_validate", "Validate training config", "Validate and normalize an Agent-generated TOML or JSON draft without starting training.", "training-config", "read",
                _object({"path": _str(), "pageTrainType": _str(), "baselinePath": _str(), "metadata": {"type": "object"}}, ("path", "pageTrainType")), self._config_validate,
            ),
            "training_config_commit": _Tool(
                "training_config_commit", "Commit training config", "Commit an approved validated draft as canonical TOML; training is never auto-started.", "training-config", "write",
                _object({"validationHash": _str(), "sourceRevision": _str(), "confirmationTicketId": _str()}, ("validationHash", "confirmationTicketId")), self._config_commit,
            ),
            "dataset_inventory": _Tool(
                "dataset_inventory", "Audit dataset", "Build a deterministic read-only inventory of images, captions, hashes and duplicates.", "dataset-review", "read",
                _object({"root": _str(), "maxFiles": {"type": "integer", "minimum": 1, "maximum": 100000}}, ("root",)), self._dataset_inventory,
            ),
            "dataset_review_images": _Tool(
                "dataset_review_images", "Review dataset images", "Review a deterministic sample with the one active remote model; no local model is used.", "dataset-review", "read",
                _object({"root": _str(), "limit": {"type": "integer", "minimum": 0, "maximum": 100}, "model": _object({"model": _str(), "vision": {"type": "boolean"}, "capabilities": {"type": "array", "items": {"type": "string"}}}, ("model", "vision"))}, ("root", "model")), self._dataset_review,
            ),
            "dataset_caption_stage": _Tool(
                "dataset_caption_stage", "Stage caption edits", "Stage caption-only overlay edits and return a diff/change-set hash for confirmation.", "caption-commit", "read",
                _object({"root": _str(), "path": _str(), "afterText": _str(), "reason": {"type": "string"}}, ("root", "path", "afterText")), self._caption_stage,
            ),
            "dataset_caption_commit": _Tool(
                "dataset_caption_commit", "Commit caption edits", "Atomically commit an approved caption change-set with backup and restore support.", "caption-commit", "write",
                _object({"root": _str(), "changeSetId": _str(), "changeSetHash": _str(), "sourceRevision": _str(), "confirmationTicketId": _str()}, ("root", "changeSetId", "changeSetHash", "confirmationTicketId")), self._caption_commit,
            ),
            "knowledge_search": _Tool(
                "knowledge_search", "Search knowledge", "Return source-backed parameter explanations with evidence and confidence metadata.", "artifacts-read", "read",
                _object({"query": _str(), "topK": {"type": "integer", "minimum": 1, "maximum": 10}, "documents": {"type": "array", "items": {"type": "object"}}}, ("query",)), self._knowledge_search,
            ),
            "civitai_search_loras": _Tool(
                "civitai_search_loras", "Search Civitai LoRAs", "Query only the official public Civitai API; popularity is discovery evidence, not causality.", "external-civitai-read", "external",
                _object({"baseModel": {"type": "string"}, "sort": {"type": "string"}, "period": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, ()), self._civitai_search,
            ),
            "civitai_cohort_report": _Tool(
                "civitai_cohort_report", "Build Civitai cohort", "Summarize disclosed LoRA parameters with missingness and popularity-bias flags.", "external-civitai-read", "read",
                _object({"records": {"type": "array", "items": {"type": "object"}}, "query": {"type": "object"}, "rankings": {"type": "array", "items": {"type": "string"}}, "timeWindows": {"type": "array", "items": {"type": "string"}}}, ("records",)), self._civitai_cohort,
            ),
            "curve_analyze": _Tool(
                "curve_analyze", "Analyze training curve", "Analyze loss/metric curves deterministically, retaining NaN/Inf and never auto-stopping training.", "metrics-read", "read",
                _object({"series": {"type": "array", "items": {"type": "object"}}, "metric": {"type": "string"}, "maxPoints": {"type": "integer", "minimum": 2, "maximum": 2000}}, ("series",)), self._curve_analyze,
            ),
            "artifact_compare": _Tool(
                "artifact_compare", "Compare artifacts", "Compare up to five artifacts under fixed prompts, seed and generation configuration.", "artifacts-read", "read",
                _object({"artifacts": {"type": "array", "items": {"type": "object"}, "maxItems": 5}, "prompts": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4}, "seed": {"type": "integer"}, "generationConfig": {"type": "object"}}, ("artifacts", "prompts", "seed", "generationConfig")), self._artifact_compare,
            ),
            "artifact_recommend": _Tool(
                "artifact_recommend", "Recommend artifact", "Rank artifacts using quality, overfit risk, stability and efficiency evidence with visible coverage.", "artifacts-read", "read",
                _object({"artifacts": {"type": "array", "items": {"type": "object"}, "maxItems": 5}, "topK": {"type": "integer", "minimum": 1, "maximum": 5}, "weights": {"type": "object"}}, ("artifacts",)), self._artifact_recommend,
            ),
        }

    def _config_template(self, session: str, call: str, p: dict[str, Any]) -> Any:
        ensure_workspace(session, purpose="training-config")
        return get_artifact_service(session).get_template(p["pageTrainType"])

    def _config_validate(self, session: str, call: str, p: dict[str, Any]) -> Any:
        ensure_workspace(session, purpose="training-config")
        return get_artifact_service(session).validate_draft(p["path"], page_train_type=p["pageTrainType"], baseline_artifact=p.get("baselinePath"), metadata=p.get("metadata"))

    def _config_commit(self, session: str, call: str, p: dict[str, Any]) -> Any:
        ticket = self.confirmations.projection(p.get("confirmationTicketId", ""))
        return get_artifact_service(session).commit_draft(p["validationHash"], confirmation_ticket=ticket, source_revision=p.get("sourceRevision"))

    def _dataset_inventory(self, session: str, call: str, p: dict[str, Any]) -> Any:
        return inventory_dataset(p["root"], max_files=p.get("maxFiles"))

    def _dataset_review(self, session: str, call: str, p: dict[str, Any]) -> Any:
        inventory = inventory_dataset(p["root"])
        sample = select_review_sample(inventory, limit=p.get("limit", 12))
        model = p["model"]
        capability = ActiveModelCapability(str(model["model"]), bool(model["vision"]), tuple(model.get("capabilities") or ("text",)))
        return review_images(inventory, sample, capability)

    def _caption_stage(self, session: str, call: str, p: dict[str, Any]) -> Any:
        key = (session, p["root"])
        overlay = self._overlays.setdefault(key, CaptionOverlay(p["root"]))
        change = overlay.stage(p["path"], p["afterText"], reason=p.get("reason", ""))
        change_set = overlay.build_change_set((change,))
        self._change_sets[(session, change_set.change_set_id)] = change_set
        return change_set

    def _caption_commit(self, session: str, call: str, p: dict[str, Any]) -> Any:
        change_set = self._change_sets.get((session, p["changeSetId"]))
        if change_set is None:
            raise DatasetReviewError("DATASET_CHANGE_SET_NOT_FOUND", "The caption change-set is unknown or expired.", status_code=404)
        if change_set.change_set_hash != p["changeSetHash"]:
            raise DatasetReviewError("DATASET_CONFIRMATION_MISMATCH", "The change-set hash does not match the staged change set.", status_code=409)
        ticket = self.confirmations.projection(p.get("confirmationTicketId", ""))
        overlay = self._overlays[(session, p["root"])]
        return overlay.commit(change_set, confirmation_ticket={**ticket, "changeSetHash": p["changeSetHash"], "sourceRevision": p.get("sourceRevision", change_set.source_revision)})

    def _knowledge_search(self, session: str, call: str, p: dict[str, Any]) -> Any:
        store = self._knowledge.setdefault(session, KnowledgeStore())
        for item in p.get("documents") or ():
            source = SourceRef(source_id=str(item["sourceId"]), title=str(item["title"]), url=str(item["url"]), version=str(item.get("version", "unknown")), scope=str(item.get("scope", "unknown")))
            store.add(KnowledgeDocument(source=source, text=str(item["text"]), tags=tuple(str(tag) for tag in item.get("tags", ()))))
        return [item.as_dict() for item in store.search(p["query"], top_k=p.get("topK", 10))]

    def _civitai_search(self, session: str, call: str, p: dict[str, Any]) -> Any:
        query = CivitaiQuery(base_model=p.get("baseModel"), sort=p.get("sort", "Most Downloaded"), period=p.get("period", "AllTime"), limit=p.get("limit", 20))
        result = CivitaiClient().search_loras(query)
        return {"records": [_as_dict(item) for item in result["records"]], "nextCursor": result.get("next_cursor"), "query": result["query"]}

    def _civitai_cohort(self, session: str, call: str, p: dict[str, Any]) -> Any:
        from mikazuki.agent_skills.civitai import normalize_lora_record
        records = [normalize_lora_record(dict(item)) for item in p["records"]]
        return build_cohort_report(records, query=p.get("query"), rankings=p.get("rankings"), time_windows=p.get("timeWindows")).as_dict()

    def _curve_analyze(self, session: str, call: str, p: dict[str, Any]) -> Any:
        metric = str(p.get("metric", "loss"))
        return analyze_curve({metric: p["series"]}, max_points=p.get("maxPoints", 200))

    def _artifact_compare(self, session: str, call: str, p: dict[str, Any]) -> Any:
        protocol = FixedComparisonProtocol(tuple(p["prompts"]), int(p["seed"]), dict(p["generationConfig"]))
        return compare_artifacts(p["artifacts"], protocol).as_dict()

    def _artifact_recommend(self, session: str, call: str, p: dict[str, Any]) -> Any:
        return recommend_artifacts(p["artifacts"], top_k=p.get("topK", 3), weights=p.get("weights")).copy()


_service: AgentToolService | None = AgentToolService(ConfirmationTicketStore())


def configure_agent_tool_service(confirmations: ConfirmationTicketStore) -> AgentToolService:
    global _service
    _service = AgentToolService(confirmations)
    return _service


def get_agent_tool_service() -> AgentToolService:
    if _service is None:
        raise RuntimeError("Agent Tool service is not configured")
    return _service


def _granted_permissions(plugin_id: str) -> frozenset[str]:
    """Fail closed: an unavailable capability context grants no Tool access."""
    from mikazuki.plugin_marketplace.api import _manager

    try:
        return _manager.capability_context(plugin_id).granted_permissions
    except Exception:
        return frozenset()


async def _resolve_plugin(request: Request) -> str:
    if request.url.hostname != "127.0.0.1":
        raise HTTPException(status_code=403, detail={"code": "LOOPBACK_REQUIRED", "message": "Host Tool traffic must use the loopback address."})
    token = request.headers.get("authorization", "")
    if not token.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"code": "HOST_TOOL_UNAUTHORIZED", "message": "Host Tool bearer token is required."})
    from mikazuki.plugin_marketplace.api import _manager
    plugin_id = _manager.plugin_for_host_tool_token(token[7:].strip())
    if not plugin_id:
        raise HTTPException(status_code=401, detail={"code": "HOST_TOOL_UNAUTHORIZED", "message": "Host Tool bearer token is invalid."})
    return plugin_id


@router.get("/definitions")
async def tool_definitions(request: Request):
    plugin_id = await _resolve_plugin(request)
    return {"ok": True, "data": {"tools": get_agent_tool_service().definitions(_granted_permissions(plugin_id))}}


@router.post("/{tool_name}")
async def execute_tool(tool_name: str, request: Request):
    plugin_id = await _resolve_plugin(request)
    session_id = request.headers.get("x-next-trainer-session-id", "")
    tool_call_id = request.headers.get("x-next-trainer-tool-call-id", "")
    if not session_id or not tool_call_id:
        raise HTTPException(status_code=400, detail={"code": "TOOL_CONTEXT_REQUIRED", "message": "Session and Tool call headers are required."})
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"code": "JSON_INVALID", "message": "Tool request body is invalid."}) from exc
    arguments = payload.get("arguments") if isinstance(payload, dict) else None
    result = await get_agent_tool_service().invoke(plugin_id, session_id, tool_call_id, tool_name, arguments or {})
    return {"ok": True, "data": result}


__all__ = ["AgentToolService", "configure_agent_tool_service", "get_agent_tool_service", "router"]

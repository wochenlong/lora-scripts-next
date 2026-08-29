from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException

from mikazuki.agent_workspace import api as workspace_api
from mikazuki.plugin_host.agent_tools import AgentToolService
from mikazuki.plugin_host.confirmation import ConfirmationTicketStore

# The full permission set declared by the plugin manifest (bridge + tools).
ALL_PERMISSIONS = frozenset({
    "model-provider",
    "training-config",
    "dataset-review",
    "caption-commit",
    "metrics-read",
    "artifacts-read",
    "external-civitai-read",
    "content-update",
})


class _StubMarketplaceManager:
    """Standalone capability context for gateway unit tests (no real install)."""

    def capability_context(self, plugin_id: str):
        return SimpleNamespace(granted_permissions=ALL_PERMISSIONS)

    def plugin_for_host_tool_token(self, token: str):
        return "plugin"


def _patch_manager(monkeypatch):
    import mikazuki.plugin_marketplace.api as marketplace_api

    monkeypatch.setattr(marketplace_api, "_manager", _StubMarketplaceManager(), raising=False)


def test_host_tool_catalog_is_stable_and_json_schema_shaped():
    service = AgentToolService(ConfirmationTicketStore())
    definitions = service.definitions(ALL_PERMISSIONS)
    names = [item["name"] for item in definitions]
    assert names == sorted(names)
    assert len(names) == len(set(names))
    assert {"training_config_template", "training_config_commit", "training_config_current", "dataset_inventory", "curve_analyze", "civitai_fetch_version"} <= set(names)
    for item in definitions:
        assert item["parameters"]["type"] == "object"
        assert item["parameters"]["additionalProperties"] is False


def test_write_tool_requires_host_confirmation(tmp_path: Path, monkeypatch):
    _patch_manager(monkeypatch)
    monkeypatch.setenv("MIKAZUKI_AGENT_WORKSPACE_ROOT", str(tmp_path))
    workspace_api._workspaces.clear()
    workspace_api._artifact_services.clear()
    service = AgentToolService(ConfirmationTicketStore())

    result = asyncio.run(
        service.invoke(
            "plugin",
            "session-1",
            "tool-call-1",
            "training_config_commit",
            {"validationHash": "sha256:missing"},
        )
    )
    assert result["state"] == "confirmation_required"
    assert result["ticket"]["pluginId"] == "plugin"
    assert result["ticket"]["toolCallId"] == "tool-call-1"


def test_read_tool_lazily_creates_scoped_workspace(tmp_path: Path, monkeypatch):
    _patch_manager(monkeypatch)
    monkeypatch.setenv("MIKAZUKI_AGENT_WORKSPACE_ROOT", str(tmp_path))
    workspace_api._workspaces.clear()
    workspace_api._artifact_services.clear()
    service = AgentToolService(ConfirmationTicketStore())
    result = asyncio.run(
        service.invoke(
            "plugin",
            "session-2",
            "tool-call-2",
            "training_config_template",
            {"pageTrainType": "sd-lora"},
        )
    )
    assert result["pageTrainType"] == "sd-lora"
    assert "session-2" in workspace_api._workspaces


def test_training_config_current_returns_user_filled_params(monkeypatch):
    import sys
    import types

    _patch_manager(monkeypatch)
    saved = {
        "lora": {
            "form": {"train_data_dir": "D:\\data\\cat", "checkpoint": "D:\\models\\sd15.ckpt"},
            "savedAt": "2026-08-29T00:00:00+00:00",
        }
    }
    stub_config = types.ModuleType("mikazuki.app.config")
    stub_config.app_config = {"saved_params": saved, "last_path": ""}
    stub_app = types.ModuleType("mikazuki.app")
    stub_app.config = stub_config
    monkeypatch.setitem(sys.modules, "mikazuki.app", stub_app)
    monkeypatch.setitem(sys.modules, "mikazuki.app.config", stub_config)

    service = AgentToolService(ConfirmationTicketStore())
    result = asyncio.run(service.invoke("plugin", "session-3", "tc-3", "training_config_current", {}))
    assert result["savedParams"]["lora"]["form"]["train_data_dir"] == "D:\\data\\cat"
    assert "savedParams" in result and "hint" in result

    filtered = asyncio.run(service.invoke("plugin", "session-3", "tc-4", "training_config_current", {"trainType": "lora"}))
    assert set(filtered["savedParams"].keys()) == {"lora"}

    missing = asyncio.run(service.invoke("plugin", "session-3", "tc-5", "training_config_current", {"trainType": "sdxl-lora"}))
    assert missing["savedParams"] == {}


def _assert_valid_tool_schema(schema: dict, path: str = "$") -> None:
    """The Host Tool catalog is embedded in EVERY model request: one malformed
    schema (e.g. a bare-string value in `properties`) makes the whole agent
    session fail at the provider.  Guard the contract here."""
    assert isinstance(schema, dict), f"{path}: schema must be an object"
    if "type" in schema:
        assert isinstance(schema["type"], str), f"{path}.type must be a string, got {schema['type']!r}"
    if "properties" in schema:
        props = schema["properties"]
        assert isinstance(props, dict), f"{path}.properties must be an object"
        for name, sub in props.items():
            assert isinstance(sub, dict), (
                f"{path}.properties.{name} must be a schema object, got "
                f"{type(sub).__name__}: {str(sub)[:60]!r}"
            )
            _assert_valid_tool_schema(sub, f"{path}.properties.{name}")
    if "items" in schema:
        _assert_valid_tool_schema(schema["items"], path + ".items")
    for kw in ("anyOf", "oneOf"):
        if kw in schema:
            assert isinstance(schema[kw], list) and schema[kw], f"{path}.{kw} must be a non-empty list"
            for i, sub in enumerate(schema[kw]):
                _assert_valid_tool_schema(sub, f"{path}.{kw}[{i}]")
    if "required" in schema:
        required = schema["required"]
        assert isinstance(required, list) and all(isinstance(x, str) for x in required), f"{path}.required must be a list of strings"
        if isinstance(schema.get("properties"), dict):
            for x in required:
                assert x in schema["properties"], f"{path}: required '{x}' missing from properties"


def test_slow_sync_handler_does_not_block_event_loop(monkeypatch):
    """A blocking sync handler (e.g. the remote vision reviewer, minutes of
    synchronous HTTP) must not stall the Host event loop: while it runs, the
    loop must stay free to serve other requests."""
    _patch_manager(monkeypatch)
    monkeypatch.setenv("MIKAZUKI_AGENT_WORKSPACE_ROOT", str(Path("tmp") / "loop-check"))
    service = AgentToolService(ConfirmationTicketStore())

    def slow_handler(self, session, call, params):
        time.sleep(1.0)
        return {"ok": True}

    # _tools() rebinds self._config_template on every call, so patch the class
    monkeypatch.setattr(AgentToolService, "_config_template", slow_handler)

    ticks = 0

    async def probe():
        nonlocal ticks
        for _ in range(200):
            await asyncio.sleep(0.01)
            ticks += 1

    async def scenario():
        nonlocal ticks
        ticks = 0
        probe_task = asyncio.ensure_future(probe())
        result = await asyncio.wait_for(
            service.invoke("plugin", "s-loop", "call-loop", "training_config_template", {"pageTrainType": "sd-lora"}),
            timeout=10.0,
        )
        probe_task.cancel()
        try:
            await probe_task
        except asyncio.CancelledError:
            pass
        return result, ticks

    result, ticks = asyncio.run(scenario())
    assert result == {"ok": True}
    # A free loop ticks the probe ~100x during the 1.0s handler; a blocked
    # loop can barely tick at all.
    assert ticks >= 30, f"event loop was blocked by the sync handler (only {ticks} probe ticks)"


def test_every_tool_schema_is_provider_safe(monkeypatch):
    """Regression: a bare-string `description` leaked into `properties` made
    dataset_review_images' schema invalid and 400'd every agent request."""
    _patch_manager(monkeypatch)
    monkeypatch.setenv("MIKAZUKI_AGENT_WORKSPACE_ROOT", str(Path("tmp") / "schema-check"))
    service = AgentToolService(ConfirmationTicketStore())
    names = sorted(service._tools())
    assert "dataset_review_images" in names
    for name in names:
        _assert_valid_tool_schema(service._tools()[name].parameters, f"tool:{name}")


def _tool_error_code(payload: str) -> str:
    try:
        detail = json.loads(payload).get("detail") or {}
    except Exception:
        return ""
    return detail.get("code", "") if isinstance(detail, dict) else ""


def test_write_ticket_follows_agent_retry_with_fresh_call_id(tmp_path: Path, monkeypatch):
    """A ticket must survive the agent re-issuing the call with a NEW tool-call
    id after the user approves (live pi sessions always get fresh ids)."""
    _patch_manager(monkeypatch)
    monkeypatch.setenv("MIKAZUKI_AGENT_WORKSPACE_ROOT", str(tmp_path))
    workspace_api._workspaces.clear()
    workspace_api._artifact_services.clear()
    service = AgentToolService(ConfirmationTicketStore())

    params = {"validationHash": "sha256:missing", "sourceRevision": "r1"}

    # a read tool first (as in the live flow: template -> validate -> commit)
    # lazily creates the scoped workspace the commit handler requires
    asyncio.run(service.invoke("plugin", "s-t", "call-0", "training_config_template", {"pageTrainType": "sd-lora"}))

    # 1. original call (id A, no ticket) -> confirmation required
    result = asyncio.run(service.invoke("plugin", "s-t", "call-A", "training_config_commit", dict(params)))
    assert result["state"] == "confirmation_required"
    ticket_id = result["ticket"]["ticketId"]
    assert result["ticket"]["paramsHash"], "ticket must carry the request identity"

    # 2. user approves
    service.confirmations.resolve(ticket_id, "approved")

    # 3. agent retries with a FRESH tool-call id + the ticket.
    #    Binding passed (we reach the handler, which rejects the unknown
    #    validation hash) instead of 409 CONFIRMATION_MISMATCH.
    try:
        asyncio.run(service.invoke("plugin", "s-t", "call-B", "training_config_commit", {**params, "confirmationTicketId": ticket_id}))
        raise AssertionError("commit with a bogus validation hash must fail")
    except HTTPException as exc:
        assert exc.status_code == 409
        assert (exc.detail or {}).get("code") == "CONFIG_CONFIRMATION_MISMATCH", exc.detail

    # 4. a failed attempt does not consume the ticket: same fresh-id retry works again
    try:
        asyncio.run(service.invoke("plugin", "s-t", "call-C", "training_config_commit", {**params, "confirmationTicketId": ticket_id}))
        raise AssertionError("commit with a bogus validation hash must fail")
    except HTTPException as exc:
        assert (exc.detail or {}).get("code") == "CONFIG_CONFIRMATION_MISMATCH", exc.detail

    # 5. simulate a successful execution consuming the ticket -> replay rejected
    service.confirmations.consume(ticket_id)
    try:
        asyncio.run(service.invoke("plugin", "s-t", "call-D", "training_config_commit", {**params, "confirmationTicketId": ticket_id}))
        raise AssertionError("consumed ticket must be rejected")
    except HTTPException as exc:
        assert exc.status_code == 409
        assert (exc.detail or {}).get("code") == "CONFIRMATION_MISMATCH", exc.detail

    # 6. parameter binding: a ticket authorizes only the exact request
    result = asyncio.run(service.invoke("plugin", "s-t", "call-E", "training_config_commit", dict(params)))
    ticket2 = result["ticket"]["ticketId"]
    service.confirmations.resolve(ticket2, "approved")
    try:
        asyncio.run(service.invoke("plugin", "s-t", "call-F", "training_config_commit", {**params, "validationHash": "sha256:other", "confirmationTicketId": ticket2}))
        raise AssertionError("different parameters must not reuse the ticket")
    except HTTPException as exc:
        assert exc.status_code == 409
        assert (exc.detail or {}).get("code") == "CONFIRMATION_MISMATCH", exc.detail


def test_civitai_fetch_version_returns_normalized_records(monkeypatch):
    import mikazuki.plugin_host.agent_tools as agent_tools_module

    _patch_manager(monkeypatch)
    seen = []

    class _FakeClient:
        def get_version(self, version_id):
            seen.append(int(version_id))
            return SimpleNamespace(as_dict=lambda: {"modelVersionId": int(version_id), "normalizedParameters": {"learning_rate": "0.001"}})

    monkeypatch.setattr(agent_tools_module, "CivitaiClient", lambda: _FakeClient())
    service = AgentToolService(ConfirmationTicketStore())
    result = asyncio.run(service.invoke("plugin", "session-4", "tc-6", "civitai_fetch_version", {"versionIds": [11, 22]}))
    assert [v["modelVersionId"] for v in result["versions"]] == [11, 22]
    assert seen == [11, 22]
    assert result["versions"][0]["normalizedParameters"]["learning_rate"] == "0.001"


def test_assets_update_tool_requires_content_update_permission():
    """Least privilege: the business-data update Tool is invisible 鈥?not merely
    rejected 鈥?unless the plugin was granted the content-update permission."""
    service = AgentToolService(ConfirmationTicketStore())
    granted = {item["name"] for item in service.definitions(ALL_PERMISSIONS)}
    assert "assets_update" in granted
    without = {item["name"] for item in service.definitions(ALL_PERMISSIONS - {"content-update"})}
    assert "assets_update" not in without


def test_assets_update_is_a_write_tool_flow_with_plugin_scoped_apply(monkeypatch):
    """Storyline: agent asks to refresh knowledge/templates -> first call asks
    for user confirmation -> approved retry updates the CALLING plugin's own
    managed namespaces and returns the publisher report."""
    import mikazuki.plugin_marketplace.api as marketplace_api

    _patch_manager(monkeypatch)
    calls: list[str] = []

    class _FakeAssets:
        def update(self, plugin_id: str):
            calls.append(plugin_id)
            return {"assetsVersion": "2026.08.29-2", "updated": ["knowledge/a.md"], "backup": None}

    monkeypatch.setattr(marketplace_api, "_assets", _FakeAssets(), raising=False)
    service = AgentToolService(ConfirmationTicketStore())

    pending = asyncio.run(service.invoke("plugin", "s-a", "call-A", "assets_update", {}))
    assert pending["state"] == "confirmation_required"
    assert pending["tool"] == "assets_update"
    assert calls == []  # nothing touched before the user approves

    ticket_id = pending["ticket"]["ticketId"]
    service.confirmations.resolve(ticket_id, "approved")
    result = asyncio.run(service.invoke("plugin", "s-a", "call-B", "assets_update", {"confirmationTicketId": ticket_id}))
    assert result["assetsVersion"] == "2026.08.29-2"
    assert calls == ["plugin"]  # applied against the calling plugin's data root


def test_assets_update_denied_without_grant(monkeypatch):
    """invoke re-checks the live capability context: a plugin that never held
    content-update cannot reach the updater by naming the tool."""
    import mikazuki.plugin_marketplace.api as marketplace_api

    class _DeniedManager:
        def capability_context(self, plugin_id: str):
            return SimpleNamespace(granted_permissions=frozenset({"model-provider"}))

        def plugin_for_host_tool_token(self, token: str):
            return "plugin"

    monkeypatch.setattr(marketplace_api, "_manager", _DeniedManager(), raising=False)
    called: list[str] = []

    class _NeverAssets:
        def update(self, plugin_id: str):
            called.append(plugin_id)
            raise AssertionError("must not be reached")

    monkeypatch.setattr(marketplace_api, "_assets", _NeverAssets(), raising=False)
    service = AgentToolService(ConfirmationTicketStore())
    try:
        asyncio.run(service.invoke("plugin", "s-d", "call-D", "assets_update", {}))
        raise AssertionError("expected permission denial")
    except HTTPException as exc:
        assert exc.status_code == 403
        assert (exc.detail or {}).get("code") == "TOOL_PERMISSION_DENIED", exc.detail
    assert called == []

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

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
    assert {"training_config_template", "training_config_commit", "dataset_inventory", "curve_analyze"} <= set(names)
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

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mikazuki.agent_workspace import api as workspace_api


def _issue_approved_ticket(store, *, tool_call_id: str):
    ticket = store.create_pending(
        plugin_id="host-ui",
        tool_call_id=tool_call_id,
        permission="training-config",
        action="training_config_commit",
        title="Commit training config",
        summary="Commit a validated training config draft.",
        params_hash="sha256:host-ui-flow",
    )
    store.resolve(ticket.ticket_id, "approved")
    return ticket.ticket_id


def test_training_config_validate_and_commit_share_host_service(monkeypatch, tmp_path):
    from mikazuki.plugin_marketplace.api import get_confirmation_store

    monkeypatch.setenv("MIKAZUKI_AGENT_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.chdir(tmp_path)
    workspace_api._workspaces.clear()
    workspace_api._artifact_services.clear()

    app = FastAPI()
    app.include_router(workspace_api.router)
    with TestClient(app) as client:
        created = client.post("/agent-workspace/workspaces", json={"sessionId": "api-session"})
        assert created.status_code == 200
        session_id = created.json()["data"]["session_id"]
        written = client.post(
            f"/agent-workspace/workspaces/{session_id}/files/write",
            json={"path": "draft.json", "content": json.dumps({"model_train_type": "sd-lora"})},
        )
        assert written.status_code == 200
        validated = client.post(
            f"/agent-workspace/workspaces/{session_id}/training-config/validate-draft",
            json={"path": "draft.json", "pageTrainType": "sd-lora"},
        )
        assert validated.status_code == 200
        validation_hash = validated.json()["data"]["validationHash"]
        committed = client.post(
            f"/agent-workspace/workspaces/{session_id}/training-config/commit-draft",
            json={
                "validationHash": validation_hash,
                "confirmationTicketId": _issue_approved_ticket(get_confirmation_store(), tool_call_id="call-1"),
                "canonicalDir": str(tmp_path / "outside"),
            },
        )
        assert committed.status_code == 200
        result = committed.json()["data"]
        assert result["autoRun"] is False
        assert (tmp_path / "config" / "autosave").is_dir()
        assert not (tmp_path / "outside").exists()


def test_commit_draft_requires_server_owned_ticket(monkeypatch, tmp_path):
    """Copilot C-1 regressions: a caller must never supply its own ticket state."""
    from mikazuki.plugin_marketplace.api import get_confirmation_store

    monkeypatch.setenv("MIKAZUKI_AGENT_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.chdir(tmp_path)
    workspace_api._workspaces.clear()
    workspace_api._artifact_services.clear()

    app = FastAPI()
    app.include_router(workspace_api.router)
    with TestClient(app) as client:
        session_id = client.post("/agent-workspace/workspaces", json={"sessionId": "api-forge"}).json()["data"]["session_id"]
        client.post(
            f"/agent-workspace/workspaces/{session_id}/files/write",
            json={"path": "draft.json", "content": json.dumps({"model_train_type": "sd-lora"})},
        )
        validated = client.post(
            f"/agent-workspace/workspaces/{session_id}/training-config/validate-draft",
            json={"path": "draft.json", "pageTrainType": "sd-lora"},
        )
        validation_hash = validated.json()["data"]["validationHash"]
        url = f"/agent-workspace/workspaces/{session_id}/training-config/commit-draft"

        # 1. forged inline ticket (the pre-fix attack) is rejected outright.
        forged = client.post(url, json={"validationHash": validation_hash, "confirmationTicket": {"state": "approved", "ticketId": "x"}})
        assert forged.status_code == 400
        assert forged.json()["detail"]["code"] == "CONFIG_TICKET_INLINE_FORBIDDEN"

        # 2. an unknown ticket id is a 404, never a commit.
        unknown = client.post(url, json={"validationHash": validation_hash, "confirmationTicketId": "no-such-ticket"})
        assert unknown.status_code == 404
        assert unknown.json()["detail"]["code"] == "CONFIRMATION_NOT_FOUND"

        # 3. a pending (not yet approved) ticket cannot commit.
        store = get_confirmation_store()
        pending = store.create_pending(
            plugin_id="host-ui", tool_call_id="call-pending", permission="training-config",
            action="training_config_commit", title="t", summary="s",
        )
        not_approved = client.post(url, json={"validationHash": validation_hash, "confirmationTicketId": pending.ticket_id})
        assert not_approved.status_code == 409

        # 3b. an APPROVED ticket for a different action cannot commit either.
        wrong_action = store.create_pending(
            plugin_id="host-ui", tool_call_id="call-other-action", permission="caption-commit",
            action="dataset_caption_commit", title="t", summary="s",
        )
        store.resolve(wrong_action.ticket_id, "approved")
        cross = client.post(url, json={"validationHash": validation_hash, "confirmationTicketId": wrong_action.ticket_id})
        assert cross.status_code == 409
        assert cross.json()["detail"]["code"] == "CONFIRMATION_MISMATCH"

        # 4. an approved ticket commits once and is rejected on replay.
        ticket_id = _issue_approved_ticket(store, tool_call_id="call-2")
        first = client.post(url, json={"validationHash": validation_hash, "confirmationTicketId": ticket_id})
        assert first.status_code == 200
        replay = client.post(url, json={"validationHash": validation_hash, "confirmationTicketId": ticket_id})
        assert replay.status_code == 409
        assert replay.json()["detail"]["code"] == "CONFIRMATION_MISMATCH"

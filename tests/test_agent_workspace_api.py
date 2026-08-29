import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mikazuki.agent_workspace import api as workspace_api


def test_training_config_validate_and_commit_share_host_service(monkeypatch, tmp_path):
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
                "confirmationTicket": {"state": "approved", "ticketId": "host-ticket"},
                "canonicalDir": str(tmp_path / "outside"),
            },
        )
        assert committed.status_code == 200
        result = committed.json()["data"]
        assert result["autoRun"] is False
        assert (tmp_path / "config" / "autosave").is_dir()
        assert not (tmp_path / "outside").exists()

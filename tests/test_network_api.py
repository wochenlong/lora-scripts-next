import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from mikazuki.networking.api import router, mutation_authority, read_authority


def test_save_reload_direct_manual_and_secrets(tmp_path, monkeypatch):
    path = tmp_path / "network.json"
    monkeypatch.setenv("NEXT_TRAINER_NETWORK_CONFIG", str(path))
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[mutation_authority] = lambda: None
    app.dependency_overrides[read_authority] = lambda: None
    with TestClient(app) as client:
        response = client.put("/network/settings", json={"mode": "manual", "https_proxy": "127.0.0.1:7890"})
        assert response.status_code == 200
        assert response.json()["data"]["effective"]["https_proxy"] == "http://127.0.0.1:7890"
        assert client.get("/network/settings").json()["data"]["settings"]["mode"] == "manual"
        assert client.put("/network/settings", json={"mode": "manual", "https_proxy": "http://u:secret@localhost:80"}).status_code == 400
        assert "secret" not in path.read_text()
        assert client.put("/network/settings", json={"mode": "direct"}).status_code == 200
        assert client.get("/network/settings").json()["data"]["effective"]["proxy_enabled"] is False
        assert client.put("/network/settings", json={"mode": "manual", "https_proxy": "http://["}).status_code == 400


def test_settings_write_requires_existing_host_authority(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXT_TRAINER_NETWORK_CONFIG", str(tmp_path / "network.json"))
    app = FastAPI(); app.include_router(router)
    with TestClient(app) as client:
        response = client.put("/network/settings", json={"mode": "direct"}, headers={"Origin": "https://evil.invalid"})
        assert response.status_code == 403
    assert not (tmp_path / "network.json").exists()

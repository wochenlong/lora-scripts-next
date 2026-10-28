"""Tests for /api/graphic_cards/live."""

from fastapi.testclient import TestClient

from mikazuki.app.application import app


def test_graphic_cards_live_reports_vram(monkeypatch):
    import torch

    gib = 1024**3
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "device_count", lambda: 2)
    monkeypatch.setattr(torch.cuda, "get_device_name", lambda i: f"FakeGPU-{i}")
    monkeypatch.setattr(
        torch.cuda,
        "mem_get_info",
        lambda i: ((8 - i * 3) * gib, 16 * gib),
    )

    client = TestClient(app)
    response = client.get("/api/graphic_cards/live")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    cards = payload["data"]["cards"]
    assert [c["name"] for c in cards] == ["FakeGPU-0", "FakeGPU-1"]
    assert cards[0]["vram_total_gb"] == 16.0
    assert cards[0]["vram_used_gb"] == 8.0
    assert cards[1]["vram_free_gb"] == 5.0


def test_graphic_cards_live_pending_without_cuda(monkeypatch):
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

    client = TestClient(app)
    response = client.get("/api/graphic_cards/live")

    assert response.status_code == 200
    assert response.json()["status"] == "pending"

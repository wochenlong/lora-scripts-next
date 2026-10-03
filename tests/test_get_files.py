from fastapi.testclient import TestClient

from mikazuki.app.application import app


def test_get_files_returns_empty_when_preset_dir_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)
    response = client.get("/api/get_files", params={"pick_type": "train-dir"})
    assert response.status_code == 200
    assert response.json()["data"]["files"] == []


def test_get_files_lists_subdirectories(tmp_path, monkeypatch):
    (tmp_path / "train" / "aki").mkdir(parents=True)
    (tmp_path / "train" / "loose.txt").write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)
    response = client.get("/api/get_files", params={"pick_type": "train-dir"})
    assert response.status_code == 200
    files = response.json()["data"]["files"]
    assert [f["name"] for f in files] == ["aki"]


def test_get_files_rejects_unknown_pick_type():
    client = TestClient(app)
    response = client.get("/api/get_files", params={"pick_type": "nope"})
    assert response.json()["status"] == "fail"

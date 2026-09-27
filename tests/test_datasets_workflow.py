import io
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mikazuki.app.application import app
from mikazuki.app.config import app_config


@pytest.fixture
def root(tmp_path, monkeypatch):
    datasets_root = tmp_path / "datasets"
    datasets_root.mkdir(parents=True)
    monkeypatch.setitem(app_config._stored, "datasets_root", str(datasets_root))
    monkeypatch.setattr(app_config, "save_config", lambda: None)
    return datasets_root


def png_bytes(color=(10, 20, 30)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, format="PNG")
    return buffer.getvalue()


def poll_overview(client: TestClient, name: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        overview = client.get(f"/api/datasets/{name}/overview").json()["data"]["overview"]
        if overview.get("state") == "ready":
            return overview
        time.sleep(0.05)
    raise AssertionError("overview did not become ready in time")


def test_full_manage_workflow_roundtrip(root: Path):
    client = TestClient(app)

    created = client.post("/api/datasets", json={"name": "wf"})
    assert created.status_code == 200

    upload = client.post(
        "/api/datasets/wf/upload",
        files=[
            ("files", ("a.png", png_bytes())),
            ("files", ("a.txt", b"1girl, solo")),
            ("files", ("sub/b.png", png_bytes((40, 50, 60)))),
        ],
    )
    assert upload.status_code == 200
    assert sorted(upload.json()["data"]["succeeded"]) == ["a.png", "a.txt", "sub/b.png"]

    overview = poll_overview(client, "wf")
    assert overview["file_count"] == 2
    assert overview["captioned_count"] == 1

    download = client.get("/api/datasets/wf/download")
    assert download.status_code == 200
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        assert sorted(archive.namelist()) == ["a.png", "a.txt", "sub/b.png"]
        assert archive.read("a.txt") == b"1girl, solo"
        assert archive.read("sub/b.png") == png_bytes((40, 50, 60))

    deleted = client.request("DELETE", "/api/datasets/wf/files", json={"paths": ["a.png"]}).json()["data"]
    assert sorted(deleted["deleted"]) == ["a.png", "a.txt"]
    restored = client.post("/api/datasets/wf/trash/restore", json={"id": deleted["batch"]}).json()["data"]
    assert sorted(restored["restored"]) == ["a.png", "a.txt"]
    assert (root / "wf" / "a.txt").read_text(encoding="utf-8") == "1girl, solo"

    removed = client.delete("/api/datasets/wf").json()["data"]
    assert not (root / "wf").exists()
    assert [d["name"] for d in client.get("/api/datasets").json()["data"]["datasets"]] == []

    brought_back = client.post("/api/datasets-trash/restore", json={"id": removed["batch"]}).json()["data"]
    assert sorted(brought_back["restored"]) == ["a.png", "a.txt", "sub/b.png"]
    assert (root / "wf" / "sub" / "b.png").read_bytes() == png_bytes((40, 50, 60))

    overview = poll_overview(client, "wf")
    assert overview["file_count"] == 2
    assert overview["captioned_count"] == 1

    emptied = client.post("/api/datasets-trash/empty", json={"confirm": True}).json()["data"]
    assert emptied["removed"] == 0

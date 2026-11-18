from mikazuki.system_resources import collect_resources


def test_collect_resources_shape(monkeypatch):
    monkeypatch.setattr(
        "mikazuki.system_resources._gpu_snapshot",
        lambda: {"name": "GPU", "vram_used_mb": 1024, "vram_total_mb": 8192, "gpu_load": 12},
    )
    monkeypatch.setattr(
        "mikazuki.system_resources._ram_snapshot",
        lambda: {"used_mb": 4096, "total_mb": 16384, "percent": 25.0},
    )
    data = collect_resources()
    assert data["gpu"]["vram_total_mb"] == 8192
    assert data["ram"]["used_mb"] == 4096


def test_collect_resources_tolerates_missing_gpu(monkeypatch):
    monkeypatch.setattr("mikazuki.system_resources._gpu_snapshot", lambda: None)
    monkeypatch.setattr(
        "mikazuki.system_resources._ram_snapshot",
        lambda: {"used_mb": 100, "total_mb": 200, "percent": 50.0},
    )
    data = collect_resources()
    assert data["gpu"] is None
    assert data["ram"]["total_mb"] == 200

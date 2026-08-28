"""ai-toolkit stdout progress parsing (ToolkitProgressBar, desc = job name)."""

import asyncio

from mikazuki.engines.ai_toolkit.progress import parse_progress


def test_parses_training_bar_with_loss_and_eta():
    lines = [
        "Running 1 job\n",
        "myrun:   0%|          | 0/2000 [00:00<?, ?it/s]\r",
        "myrun:  12%|█▏        | 240/2000 [00:30<03:40,  3.99it/s, lr: 1.0e-04 loss: 1.234e-01]",
    ]
    progress = parse_progress(lines, "myrun")
    assert progress["percent"] == 12
    assert progress["step"] == 240
    assert progress["total_steps"] == 2000
    assert progress["elapsed"] == "00:30"
    assert progress["eta"] == "03:40"
    assert progress["loss"] == 0.1234


def test_ignores_other_bars():
    lines = [
        "Caching latents:  50%|████    | 3/6 [00:01<00:01,  2.00it/s]",
        "myrun:   5%|▌         | 100/2000 [00:10<03:10, 10.0it/s, lr: 1.0e-04 loss: 5.0e-01]",
        "Sampling:  40%|███      | 8/20 [00:02<00:03,  4.0it/s]",
    ]
    progress = parse_progress(lines, "myrun")
    assert progress["step"] == 100
    assert progress["total_steps"] == 2000


def test_picks_latest_bar_fragment():
    lines = [
        "myrun:  10%|█         | 200/2000 [01:00<09:00, 3.3it/s, loss: 2.0e-01]\r"
        "myrun:  11%|█         | 220/2000 [01:06<08:54, 3.3it/s, loss: 1.9e-01]",
    ]
    progress = parse_progress(lines, "myrun")
    assert progress["step"] == 220
    assert progress["loss"] == 0.19


def test_empty_without_matching_job_name():
    lines = ["other:  12%|█▏| 240/2000 [00:30<03:40, 3.99it/s, loss: 1.0e-01]"]
    assert parse_progress(lines, "myrun") == {}
    assert parse_progress(lines, "") == {}


def test_missing_loss_and_eta_are_optional():
    lines = ["myrun:   0%|          | 0/2000 [00:00<?, ?it/s]"]
    progress = parse_progress(lines, "myrun")
    assert progress["step"] == 0
    assert "loss" not in progress
    assert "eta" not in progress


def test_metrics_endpoint_uses_ai_toolkit_parser(monkeypatch, tmp_path):
    from mikazuki.app import api
    from mikazuki.tasks import tm

    class _Task:
        metadata = {
            "backend": "ai-toolkit",
            "output_name": "myrun",
            "output_dir": str(tmp_path / "out"),
            "logging_dir": str(tmp_path / "logs"),
        }

    tm.tasks["t-aitk-progress"] = _Task()
    try:
        monkeypatch.setattr(
            api.train_log_hub,
            "tail",
            lambda task_id, n: [
                "myrun:  12%|█▏        | 240/2000 [00:30<03:40,  3.99it/s, lr: 1.0e-04 loss: 1.234e-01]"
            ],
        )
        response = asyncio.run(api.task_metrics("t-aitk-progress"))
        assert response.data["progress"]["step"] == 240
        assert response.data["progress"]["total_steps"] == 2000
    finally:
        tm.tasks.pop("t-aitk-progress", None)


def test_metrics_endpoint_falls_back_for_packs_without_progress_hook(monkeypatch, tmp_path):
    from mikazuki.app import api
    from mikazuki.tasks import tm

    class _Task:
        metadata = {"backend": "musubi"}

    tm.tasks["t-musubi-progress"] = _Task()
    try:
        monkeypatch.setattr(
            api.train_log_hub,
            "tail",
            lambda task_id, n: ["steps:  12%|█▏        | 120/1000 [00:30<03:40, 3.99it/s, avr_loss=0.123]"],
        )
        response = asyncio.run(api.task_metrics("t-musubi-progress"))
        assert response.data["progress"]["step"] == 120
        assert response.data["progress"]["total_steps"] == 1000
    finally:
        tm.tasks.pop("t-musubi-progress", None)


def test_metrics_endpoint_unknown_backend_falls_back(monkeypatch, tmp_path):
    from mikazuki.app import api
    from mikazuki.tasks import tm

    class _Task:
        metadata = {"backend": "no-such-engine"}

    tm.tasks["t-unknown-progress"] = _Task()
    try:
        monkeypatch.setattr(
            api.train_log_hub,
            "tail",
            lambda task_id, n: ["steps:  50%|█████     | 50/100 [00:10<00:10, 5.0it/s]"],
        )
        response = asyncio.run(api.task_metrics("t-unknown-progress"))
        assert response.data["progress"]["step"] == 50
    finally:
        tm.tasks.pop("t-unknown-progress", None)

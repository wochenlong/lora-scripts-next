"""MOSS insights isolation without model imports or real TensorBoard events."""
from pathlib import Path

import pytest

from mikazuki.utils import task_insights


@pytest.fixture
def moss_metadata(tmp_path):
    output = tmp_path / "output"
    logs = tmp_path / "logs" / "moss"
    output.mkdir()
    logs.mkdir(parents=True)
    config = tmp_path / "ui-config.toml"
    # UI values can differ from the normalized runtime paths and output stem.
    config.write_text(
        'output_dir = "./wrong-output"\n'
        'logging_dir = "./logs"\n'
        'output_name = "portrait.safetensors"\n',
        encoding="utf-8",
    )
    return {
        "backend": "moss", "config_path": str(config),
        "output_dir": str(output), "logging_dir": str(logs),
        "output_name": "portrait",
    }


def test_moss_uses_normalized_runtime_metadata(moss_metadata, monkeypatch):
    def unexpected_config_read(_metadata):
        pytest.fail("MOSS insights must not reinterpret the raw UI config")

    monkeypatch.setattr(task_insights, "resolve_task_config", unexpected_config_read)
    assert task_insights.resolve_task_dirs(moss_metadata) == {
        "output_dir": Path(moss_metadata["output_dir"]).resolve(),
        "logging_dir": Path(moss_metadata["logging_dir"]).resolve(),
        "output_name": "portrait",
    }


def test_moss_does_not_reuse_another_engines_preview_cache(moss_metadata):
    output = Path(moss_metadata["output_dir"])
    image = output / "portrait_e1.png"
    image.write_bytes(b"synthetic preview fixture")
    # DiffSynth uses the same metadata paths and the shared non-toolkit cache.
    other = {**moss_metadata, "backend": "diffsynth"}
    assert [item["name"] for item in task_insights.list_preview_images(other)] == [image.name]
    assert task_insights.list_preview_images(moss_metadata) == []
    assert task_insights.resolve_preview_image(moss_metadata, image.name) is None


def test_moss_never_scans_tensorboard_files(moss_metadata, monkeypatch):
    event = Path(moss_metadata["logging_dir"]) / "events.out.tfevents.other-engine"
    event.write_bytes(b"synthetic event fixture")

    def unexpected_scan(*_args, **_kwargs):
        pytest.fail("MOSS has no TensorBoard writer and must not scan event files")

    monkeypatch.setattr(task_insights, "resolve_task_dirs", unexpected_scan)
    monkeypatch.setattr(Path, "rglob", unexpected_scan)
    monkeypatch.setattr(task_insights, "_read_run_scalars", unexpected_scan)
    assert task_insights.read_loss_scalars(moss_metadata) == {}

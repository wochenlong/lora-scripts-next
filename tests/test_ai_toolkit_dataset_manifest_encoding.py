import json

from mikazuki.engines.ai_toolkit.adapter import AdaptedConfig, write_job


def test_manifest_roundtrips_through_windows_default_encoding(tmp_path):
    manifest = tmp_path / "dataset.json"
    items = {"D:/\u8bad\u7ec3/001.png": {"caption": "\u4eba\u7269, blue sky"}}
    adapted = AdaptedConfig(config={}, dataset_manifests={str(manifest): items})

    write_job(adapted, tmp_path / "job.yaml")

    # The pinned upstream uses open(path, "r") without an encoding.
    assert json.loads(manifest.read_bytes().decode("cp936")) == items

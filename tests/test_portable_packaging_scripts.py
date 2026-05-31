from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_packaged_update_helper_delegates_to_root_updater():
    script = (ROOT / "build-scripts" / "build_portable.ps1").read_text(
        encoding="utf-8"
    )

    assert "Update-SD-Trainer.bat" in script
    assert "call `\"%~dp0..\\Update-SD-Trainer.bat`\" %*" in script
    assert "git pull`r`n" not in script


def test_portable_builder_embeds_git_metadata_for_updates():
    script = (ROOT / "build-scripts" / "build_portable.ps1").read_text(
        encoding="utf-8"
    )

    assert "Clone-SDTrainerGitMetadata" in script
    assert "SD-Trainer\\.git" in script
    assert "--depth=1" in script


def test_portable_builder_initializes_dataset_tag_editor_before_copy():
    script = (ROOT / "build-scripts" / "build_portable.ps1").read_text(
        encoding="utf-8"
    )

    assert "mikazuki/dataset-tag-editor" in script
    assert "dataset-tag-editor\\scripts\\launch.py" in script


def test_portable_launcher_keeps_default_hf_mirror_for_skip_prepare_mode():
    launcher = (ROOT / "scripts" / "portable" / "launch_portable.bat").read_text(
        encoding="utf-8"
    )

    assert "HF_ENDPOINT" in launcher
    assert "https://hf-mirror.com" in launcher


def test_portable_builder_bundles_visible_tagger_models_directory():
    script = (ROOT / "build-scripts" / "build_portable.ps1").read_text(
        encoding="utf-8"
    )
    launcher = (ROOT / "scripts" / "portable" / "launch_portable.bat").read_text(
        encoding="utf-8"
    )

    assert "tagger-models" in script
    assert "tagger-models\\wd14" in script
    assert "tagger-models\\vlm" in script
    assert "--tagger-models-dir" in script
    assert "MIKAZUKI_TAGGER_MODELS_DIR" in launcher

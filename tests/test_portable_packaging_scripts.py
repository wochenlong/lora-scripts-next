from pathlib import Path
import re
import runpy


ROOT = Path(__file__).resolve().parents[1]


def test_bootstrap_download_manifest_matches_git_allowlist():
    common = (ROOT / "scripts/portable/portable_updater_common.ps1").read_text(
        encoding="utf-8-sig"
    )
    destinations = re.findall(r'Dest = "Next-Trainer/([^"]+)"', common)
    helper = runpy.run_path(str(ROOT / "scripts/portable/portable_git.py"))
    assert set(destinations) == set(helper["BOOTSTRAP_FILES"])
    for path in destinations:
        assert (ROOT / path).is_file(), path


def test_packaged_update_helper_delegates_to_root_updater():
    script = (ROOT / "build-scripts" / "build_portable.ps1").read_text(
        encoding="utf-8"
    )

    assert "Update-Next-Trainer.bat" in script
    assert "call `\"%~dp0..\\Update-Next-Trainer.bat`\" %*" in script
    assert "git pull`r`n" not in script


def test_portable_builder_embeds_git_metadata_for_updates():
    script = (ROOT / "build-scripts" / "build_portable.ps1").read_text(
        encoding="utf-8"
    )

    assert "Clone-SDTrainerGitMetadata" in script
    assert 'portable_git.py") seed --source $ProjectRoot' in script
    assert 'portable_git.py") verify --trainer-dir $sdtDir' in script
    assert 'tests/test_portable_git_behavior.py' in script


def test_portable_builder_no_longer_requires_dataset_tag_editor():
    script = (ROOT / "build-scripts" / "build_portable.ps1").read_text(
        encoding="utf-8"
    )
    copy_project = (ROOT / "build-scripts" / "03-copy-project.ps1").read_text(
        encoding="utf-8"
    )
    updater = (ROOT / "scripts" / "portable" / "templates" / "Update-Next-Trainer.bat").read_text(
        encoding="utf-8"
    )
    run_gui_sh = (ROOT / "run_gui.sh").read_text(encoding="utf-8")

    assert "dataset-tag-editor" not in script
    assert "Initialize-DatasetTagEditor" not in script
    assert "dataset-tag-editor" not in updater
    assert "try_submodule" not in updater
    assert "git submodule update" not in copy_project
    assert "git submodule update" not in run_gui_sh


def test_portable_launcher_uses_auto_hub_backend_without_forcing_modelscope():
    launcher = (ROOT / "scripts" / "portable" / "launch_portable.bat").read_text(
        encoding="utf-8"
    )

    assert "MIKAZUKI_HUB_BACKEND=auto" in launcher
    assert "MIKAZUKI_HUB_BACKEND=modelscope" not in launcher
    assert "MIKAZUKI_TOKENIZER_CACHE_DIR" in launcher
    assert "prefetch_sdxl_tokenizer.py" in launcher
    assert "-u gui.py" in launcher
    assert 'gui.py --skip-prepare-environment' in launcher
    gui_line = next(line for line in launcher.splitlines() if "gui.py" in line and "PYTHON_EXE" in line)
    assert "2>>" not in gui_line


def test_portable_builder_bundles_sdxl_tokenizer_cache():
    script = (ROOT / "build-scripts" / "build_portable.ps1").read_text(
        encoding="utf-8"
    )

    assert "prefetch_sdxl_tokenizer.py" in script
    assert "tokenizer-cache" in script
    assert "openai_clip-vit-large-patch14" in script


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


def test_portable_archive_temporarily_removes_root_data_junctions():
    script = (ROOT / "build-scripts" / "build_portable.ps1").read_text(
        encoding="utf-8"
    )

    for name in ("sd-models", "output", "logs", "train"):
        assert name in script
    assert "$archiveJunctionNames" in script
    assert "rmdir" in script
    assert "ReparsePoint" in script
    assert "$pythonExe -s $linkScript --trainer-dir $sdtDir" in script
    assert "refusing to archive non-empty generated data directory" in script
    assert 'Where-Object { $_.Name -notin @(".gitkeep", ".keep") }' in script
    assert "-xr!" not in script


def test_portable_builder_bundles_dual_update_scripts():
    script = (ROOT / "build-scripts" / "build_portable.ps1").read_text(
        encoding="utf-8"
    )
    release_ps1 = (
        ROOT / "scripts" / "portable" / "update_from_release.ps1"
    ).read_text(encoding="utf-8")

    assert "Update-Next-Trainer-Release.bat" in script
    assert "update_from_release.bat" in script
    assert "Next-Trainer-v*.7z" in release_ps1 or "Next-Trainer-v" in release_ps1
    assert "SD-Trainer-v*.7z" in release_ps1 or "SD-Trainer-v" in release_ps1
    assert "extensions" in release_ps1
    assert '"/XD", "config", "sd-models", "output", "logs", "train"' in release_ps1
    assert 'assets\\config.json' in release_ps1


def test_release_updater_forces_overwrite_for_same_version_republish():
    release_ps1 = (
        ROOT / "scripts" / "portable" / "update_from_release.ps1"
    ).read_text(encoding="utf-8")

    assert "/XO" not in release_ps1
    assert "/IS" in release_ps1
    assert "portable_release_sync" in release_ps1
    assert "PORTABLE_BUILD" in release_ps1


def test_portable_verifier_checks_current_user_data_exclusions():
    verifier = (
        ROOT / "scripts" / "portable" / "verify_portable_updaters.ps1"
    ).read_text(encoding="utf-8-sig")

    assert '"/XD", "config"' in verifier
    assert "assets\\config.json" in verifier
    assert "missingUserDataMarkers" in verifier


def test_portable_builder_writes_portable_build_metadata():
    script = (ROOT / "build-scripts" / "build_portable.ps1").read_text(
        encoding="utf-8"
    )

    assert "Write-PortableBuildMetadata" in script
    assert "PORTABLE_BUILD" in script
    assert "scripts\\portable\\templates" in script


def test_portable_git_updater_is_not_legacy_pull_only():
    bat = (ROOT / "build-scripts" / "templates" / "Update-Next-Trainer.bat").read_text(
        encoding="utf-8"
    )
    assert "Pulling latest code" not in bat
    assert 'not exist ".git\\"' in bat
    assert "print_version_info" in bat
    assert "UPDATER_VERSION" in bat


def test_portable_updater_version_file_exists():
    version_file = ROOT / "scripts" / "portable" / "UPDATER_VERSION"
    assert version_file.is_file()
    text = version_file.read_text(encoding="utf-8").strip()
    assert text.isdigit()
    assert int(text) >= 1


def test_portable_updater_manifest_paths_exist():
    common = (
        ROOT / "scripts" / "portable" / "portable_updater_common.ps1"
    ).read_text(encoding="utf-8")
    assert "Get-PortableUpdaterManifest" in common
    for rel in (
        "build-scripts/templates/Update-Next-Trainer.bat",
        "scripts/portable/bootstrap_portable_updaters.ps1",
        "scripts/portable/UPDATER_VERSION",
        "scripts/portable/portable_git.py",
        ".gitignore",
        ".gitattributes",
    ):
        assert rel in common
    bat = (ROOT / "build-scripts" / "templates" / "Update-Next-Trainer.bat").read_text(
        encoding="utf-8"
    )
    assert "bootstrap_updater_scripts" in bat
    assert "--no-bootstrap" in bat


def test_git_updater_templates_delegate_to_safe_helper():
    source = (ROOT / "build-scripts/templates/Update-Next-Trainer.bat").read_bytes()
    assert source == (ROOT / "scripts/portable/templates/Update-Next-Trainer.bat").read_bytes()
    text = source.decode("utf-8")
    assert '"%GIT_HELPER%" update --trainer-dir "%PROJECT_DIR%"' in text
    assert "git stash" not in text
    assert "git reset" not in text
    assert not any(line.strip().startswith("git pull ") for line in text.splitlines())

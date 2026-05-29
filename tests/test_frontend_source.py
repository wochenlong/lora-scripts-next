import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_source_contract_is_declared():
    result = subprocess.run(
        [sys.executable, "scripts/verify_frontend_source.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "frontend source contract OK" in result.stdout


def test_frontend_source_settings_page_owns_tagger_api_config():
    settings = (ROOT / "frontend" / "source" / "src" / "settings.ts").read_text(
        encoding="utf-8"
    )
    main = (ROOT / "frontend" / "source" / "src" / "main.ts").read_text(encoding="utf-8")

    assert "SettingsPage" in main
    assert 'route.path === "/other/settings.html"' in main
    assert "ui-configs" in settings
    assert "dataset_tagger_api_endpoint" in settings
    assert "dataset_tagger_api_key" in settings
    assert "dataset_tagger_api_model" in settings
    assert "dataset_tagger_api_prompt" in settings
    assert 'type: "password"' in settings
    assert "sd-trainer-ui-advanced-links" in settings
    assert "showLegacyTagEditor" in settings
    assert "showTensorboard" in settings


def test_frontend_source_declares_anima_route_contracts():
    anima = (ROOT / "frontend" / "source" / "src" / "anima.ts").read_text(
        encoding="utf-8"
    )
    main = (ROOT / "frontend" / "source" / "src" / "main.ts").read_text(encoding="utf-8")

    assert "AnimaRoutePage" in main
    assert "isAnimaRoute" in main
    for term in [
        "/lora/sd3.html",
        "/lora/anima-finetune.html",
        "anima-lora",
        "anima-finetune",
        "mikazuki/schema/sd3-lora.ts",
        "mikazuki/schema/anima-finetune.ts",
        "scripts/dev/anima_train_network.py",
        "scripts/dev/anima_train.py",
    ]:
        assert term in anima


def test_frontend_source_owns_native_tag_editor_entry():
    native_editor = (
        ROOT / "frontend" / "source" / "src" / "nativeTagEditor.ts"
    ).read_text(encoding="utf-8")
    entry = (
        ROOT / "frontend" / "source" / "public" / "assets" / "dataset-editor-entry.js"
    ).read_text(encoding="utf-8")
    runtime = (
        ROOT / "frontend" / "source" / "public" / "assets" / "dataset-editor.js"
    ).read_text(encoding="utf-8")
    styles = (
        ROOT / "frontend" / "source" / "public" / "assets" / "dataset-editor.css"
    ).read_text(encoding="utf-8")
    main = (ROOT / "frontend" / "source" / "src" / "main.ts").read_text(encoding="utf-8")

    assert "NativeTagEditorPage" in main
    assert 'route.path === "/native-tageditor.html"' in main
    assert "/assets/dataset-editor-entry.js" in native_editor
    assert "/assets/dataset-editor.css" in native_editor
    assert "sd-dataset-editor-script" in native_editor
    assert "sd-native-editor-entry" in entry
    assert "de-shell-embedded" in entry
    assert "de-shell-embedded" in styles
    for term in [
        "/api/dataset-editor/scan",
        "/api/dataset-editor/caption",
        "/api/dataset-editor/batch",
        "/api/dataset-editor/tag",
        "/api/dataset-editor/undo",
        "/api/dataset-editor/redo",
        "dataset_tagger_api_endpoint",
        "dataset_tagger_api_key",
    ]:
        assert term in runtime


def test_frontend_source_declares_browser_smoke_script():
    package = (ROOT / "frontend" / "source" / "package.json").read_text(
        encoding="utf-8"
    )
    smoke = (
        ROOT / "frontend" / "source" / "scripts" / "smoke-source-frontend.spec.mjs"
    ).read_text(encoding="utf-8")

    assert '"smoke": "playwright test' in package
    assert "/native-tageditor.html" in smoke
    assert "sd-native-editor-entry" in smoke
    assert "/lora/anima-finetune.html" in smoke

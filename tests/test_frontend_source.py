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
        "animaForm",
        "sd-trainer-source-anima-configs",
        "/api/run",
        "pretrained_model_name_or_path",
        "train_data_dir",
        "output_dir",
        "output_name",
        "max_train_epochs",
        "mixed_precision",
        "enable_preview",
        "vae",
        "qwen3",
        "t5_tokenizer_path",
        "attn_mode",
        "timestep_sampling",
        "discrete_flow_shift",
        "train_batch_size",
        "gradient_checkpointing",
        "gradient_accumulation_steps",
        "cache_latents",
        "cache_latents_to_disk",
        "cache_text_encoder_outputs",
        "positive_prompts",
        "negative_prompts",
        "sample_width",
        "sample_height",
        "sample_every_n_epochs",
        "caption_extension",
        "prefer_json_caption",
        "previewToml",
        "anima-preview-code",
        "Save Config",
        "Load Config",
    ]:
        assert term in anima


def test_frontend_source_has_training_schema_renderer():
    renderer_path = ROOT / "frontend" / "source" / "src" / "trainingRenderer.ts"
    assert renderer_path.exists()
    renderer = renderer_path.read_text(encoding="utf-8")
    anima = (ROOT / "frontend" / "source" / "src" / "anima.ts").read_text(
        encoding="utf-8"
    )

    for term in [
        "TrainingFieldSpec",
        "renderTrainingField",
        "renderTrainingSection",
        "renderTrainingWorkbench",
        "renderParameterPreview",
        "renderRunControls",
        "previewToml",
        "tomlValue",
        "renderTrainingFields",
        "renderTrainingFieldRow",
        "description",
        "hidden",
        "disabled",
        "training-field-description",
        "anima-workbench",
        "anima-form-panel",
        "anima-preview-panel",
        "Parameter Preview",
        "kind: \"text\"",
        "kind: \"number\"",
        "kind: \"checkbox\"",
        "kind: \"select\"",
        "kind: \"textarea\"",
    ]:
        assert term in renderer
    assert "./trainingRenderer" in anima
    assert "renderTrainingField" in anima
    assert "function tomlValue" not in anima


def test_frontend_source_owns_native_tag_editor_entry():
    native_editor = (
        ROOT / "frontend" / "source" / "src" / "nativeTagEditor.ts"
    ).read_text(encoding="utf-8")
    entry = (
        ROOT / "frontend" / "source" / "src" / "nativeDatasetEditorMarkup.ts"
    ).read_text(encoding="utf-8")
    runtime = (
        ROOT / "frontend" / "source" / "src" / "nativeDatasetEditorRuntime.ts"
    ).read_text(encoding="utf-8")
    styles = (
        ROOT / "frontend" / "source" / "src" / "nativeDatasetEditor.css"
    ).read_text(encoding="utf-8")
    main = (ROOT / "frontend" / "source" / "src" / "main.ts").read_text(encoding="utf-8")

    assert "NativeTagEditorPage" in main
    assert 'route.path === "/native-tageditor.html"' in main
    assert 'route.path === "/dataset-editor.html"' in main
    assert "nativeDatasetEditorMarkup" in native_editor
    assert not (
        ROOT / "frontend" / "source" / "public" / "assets" / "dataset-editor-entry.js"
    ).exists()
    assert './nativeDatasetEditor.css' in native_editor
    assert not (
        ROOT / "frontend" / "source" / "public" / "assets" / "dataset-editor.css"
    ).exists()
    assert "nativeDatasetEditorRuntime" in native_editor
    assert "sd-dataset-editor-script" not in native_editor
    assert not (
        ROOT / "frontend" / "source" / "public" / "assets" / "dataset-editor.js"
    ).exists()
    assert "sd-native-editor-entry" in native_editor
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
    assert "/dataset-editor.html" in smoke
    assert "sd-native-editor-entry" in smoke
    assert "/tagger.html" in smoke
    assert "sd-tagger-dock" in smoke
    assert "/lora/anima-finetune.html" in smoke
    assert "anima-train-form" in smoke


def test_frontend_source_owns_tagger_page_and_progress_asset():
    tagger = (ROOT / "frontend" / "source" / "src" / "tagger.ts").read_text(
        encoding="utf-8"
    )
    main = (ROOT / "frontend" / "source" / "src" / "main.ts").read_text(encoding="utf-8")

    assert "TaggerPage" in main
    assert 'route.path === "/tagger.html"' in main
    for term in [
        "taggerForm",
        "taggerStatus",
        "interrogator_model",
        "wd14-convnextv2-v2",
        "threshold",
        "character_threshold",
        "batch_output_action_on_conflict",
        "/api/tagger/status",
        "/api/tagger/prefetch",
        "/api/tagger/cancel",
        "/api/tagger/reset",
        "/api/interrogate",
        "sd-tagger-dock",
    ]:
        assert term in tagger
    assert "/assets/tagger-progress.js" not in tagger
    assert not (
        ROOT / "frontend" / "source" / "public" / "assets" / "tagger-progress.js"
    ).exists()

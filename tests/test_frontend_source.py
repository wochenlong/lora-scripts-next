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


def test_frontend_source_dist_sync_script_is_guarded():
    script_path = ROOT / "scripts" / "sync_frontend_source_dist.py"
    assert script_path.exists()
    script = script_path.read_text(encoding="utf-8")

    for term in [
        "build/frontend-source-dist",
        "frontend/dist",
        "--apply",
        "--backup",
        "scripts/verify_frontend_source.py",
        "shutil.copytree",
        "source dist sync plan OK",
    ]:
        assert term in script


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
    anima_schema = (
        ROOT / "frontend" / "source" / "src" / "animaSchema.ts"
    ).read_text(encoding="utf-8")
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
        "llm_adapter_path",
        "resume",
        "qwen3_max_token_length",
        "t5_max_token_length",
        "attn_mode",
        "timestep_sampling",
        "sigmoid_scale",
        "discrete_flow_shift",
        "weighting_scheme",
        "enable_bucket",
        "min_bucket_reso",
        "max_bucket_reso",
        "bucket_reso_steps",
        "train_batch_size",
        "gradient_checkpointing",
        "gradient_accumulation_steps",
        "network_train_unet_only",
        "network_train_text_encoder_only",
        "lr_scheduler",
        "lr_warmup_steps",
        "cache_latents",
        "cache_latents_to_disk",
        "cache_text_encoder_outputs",
        "positive_prompts",
        "negative_prompts",
        "sample_width",
        "sample_height",
        "sample_steps",
        "sample_sampler",
        "sample_scheduler",
        "sample_at_first",
        "sample_every_n_epochs",
        "caption_extension",
        "prefer_json_caption",
        "logit_mean",
        "logit_std",
        "mode_scale",
        "split_attn",
        "vae_chunk_size",
        "vae_disable_cache",
        "unsloth_offload_checkpointing",
        "fp8_base",
        "fp8_base_unet",
        "persistent_data_loader_workers",
        "max_data_loader_n_workers",
        "text_encoder_batch_size",
        "disable_mmap_load_safetensors",
        "blocks_to_swap",
        "cpu_offload_checkpointing",
        "optimizer_args_custom",
        "network_args_custom",
        "previewToml",
        "anima-preview-code",
        "Save Config",
        "Load Config",
        "Reset Config",
        "Export Config",
        "Import Config",
        "resetForm",
        "exportConfig",
        "importConfigInput",
        "importConfigFile",
    ]:
        assert term in anima or term in anima_schema


def test_frontend_source_has_training_schema_renderer():
    renderer_path = ROOT / "frontend" / "source" / "src" / "trainingRenderer.ts"
    assert renderer_path.exists()
    renderer = renderer_path.read_text(encoding="utf-8")
    anima = (ROOT / "frontend" / "source" / "src" / "anima.ts").read_text(
        encoding="utf-8"
    )
    anima_schema = (
        ROOT / "frontend" / "source" / "src" / "animaSchema.ts"
    ).read_text(encoding="utf-8")

    for term in [
        "TrainingFieldSpec",
        "TrainingSectionItem",
        "TrainingSectionSpec",
        "TrainingVisibilityRule",
        "renderTrainingField",
        "renderTrainingSection",
        "renderTrainingSectionSpec",
        "renderTrainingSchemaSections",
        "renderTrainingWorkbench",
        "renderParameterPreview",
        "renderRunControls",
        "previewToml",
        "tomlValue",
        "renderTrainingFields",
        "renderTrainingFieldRow",
        'kind: "row"',
        "description",
        "hidden",
        "disabled",
        "visibleWhen",
        "matchesVisibilityRule",
        "equals",
        "notEquals",
        "role?:",
        "data-training-role",
        "sd-training-path-browse",
        "Browse",
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
        "kind: \"table\"",
        "training-table-field",
        "Add Row",
        "Remove",
    ]:
        assert term in renderer
    assert "./trainingRenderer" in anima
    assert "./animaSchema" in anima
    assert "AnimaForm" in anima_schema
    assert "TrainingSectionSpec<AnimaForm>" in anima_schema
    assert "animaModelAssetSection" in anima_schema
    assert "animaDatasetOutputSection" in anima_schema
    assert "animaTrainingSection" in anima_schema
    assert "animaLoraAdapterSection" in anima_schema
    assert "animaParametersSection" in anima_schema
    assert "animaCacheSection" in anima_schema
    assert "animaPreviewSection" in anima_schema
    assert "animaSectionsForPlan" in anima_schema
    assert "renderTrainingSchemaSections(animaForm, animaSectionsForPlan(plan))" in anima
    assert 'visibleWhen: { key: "enable_preview", equals: true }' in anima_schema
    assert 'visibleWhen: { key: "weighting_scheme", equals: "logit_normal" }' in anima_schema
    assert 'visibleWhen: { key: "weighting_scheme", equals: "mode" }' in anima_schema
    assert 'kind: "table"' in anima_schema
    assert "role:" in anima_schema
    assert '"file"' in anima_schema
    assert '"folder"' in anima_schema
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


def test_frontend_source_owns_static_utility_pages():
    static_pages = (
        ROOT / "frontend" / "source" / "src" / "staticPages.ts"
    ).read_text(encoding="utf-8")
    main = (ROOT / "frontend" / "source" / "src" / "main.ts").read_text(encoding="utf-8")
    smoke = (
        ROOT / "frontend" / "source" / "scripts" / "smoke-source-frontend.spec.mjs"
    ).read_text(encoding="utf-8")

    assert "StaticInfoPage" in main
    assert "isStaticInfoRoute" in main
    for term in [
        "/tensorboard.html",
        "/lora/tools.html",
        "/task.html",
        "/help/guide.html",
        "/other/about.html",
        "/other/changelog.html",
        "source-static-page",
        "source-static-actions",
        "Open TensorBoard",
        "Launch tensorboard.py",
        "scripts/run_gui.py",
        "frontend/source",
    ]:
        assert term in static_pages
    for route in [
        "/tensorboard.html",
        "/lora/tools.html",
        "/task.html",
        "/help/guide.html",
        "/other/about.html",
        "/other/changelog.html",
    ]:
        assert route in smoke
    assert "source-static-page" in smoke


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

import json
import importlib.util
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


def test_frontend_source_route_titles_are_readable():
    routes = json.loads(
        (ROOT / "frontend" / "source" / "src" / "routes.json").read_text(
            encoding="utf-8"
        )
    )
    titles = {route["path"]: route["title"] for route in routes}

    assert titles["/tagger.html"] == "数据集打标"
    assert titles["/tageditor.html"] == "经典标签编辑"
    assert titles["/native-tageditor.html"] == "原生标签编辑"
    assert titles["/dataset-editor.html"] == "原生标签编辑 Debug"
    assert titles["/other/settings.html"] == "UI 设置"
    assert titles["/lora/anima-finetune.html"] == "全量微调"
    assert titles["/help/guide.html"] == "新手上路"
    assert titles["/other/changelog.html"] == "更新日志"


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


def test_frontend_source_dist_sync_preserves_legacy_tageditor_island(tmp_path):
    module_path = ROOT / "scripts" / "sync_frontend_source_dist.py"
    spec = importlib.util.spec_from_file_location("sync_frontend_source_dist", module_path)
    assert spec and spec.loader
    sync_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync_module)

    root = tmp_path
    source = root / "build" / "frontend-source-dist"
    target = root / "frontend" / "dist"
    (source / "assets").mkdir(parents=True)
    (target / "assets").mkdir(parents=True)
    (source / "index.html").write_text("source index", encoding="utf-8")
    (source / "tageditor.html").write_text("source placeholder", encoding="utf-8")
    (source / "native-tageditor.html").write_text("source native editor", encoding="utf-8")
    (source / "assets" / "index-source.js").write_text("source", encoding="utf-8")
    (target / "tageditor.html").write_text(
        'legacy classic editor <a href="/native-tageditor.html">native</a>',
        encoding="utf-8",
    )
    (target / "native-tageditor.html").write_text("legacy native editor", encoding="utf-8")
    for asset in [
        "app.547295de.js",
        "style.874872ce.css",
        "tageditor.html.173f1b6a.js",
        "tageditor.html.66da263e.js",
    ]:
        (target / "assets" / asset).write_text(f"legacy {asset}", encoding="utf-8")

    sync_module.sync_dist(source, target, backup=True, root=root)

    assert (target / "index.html").read_text(encoding="utf-8") == "source index"
    assert "legacy classic editor" in (target / "tageditor.html").read_text(encoding="utf-8")
    assert (target / "native-tageditor.html").read_text(encoding="utf-8") == "source native editor"
    for asset in [
        "app.547295de.js",
        "style.874872ce.css",
        "tageditor.html.173f1b6a.js",
        "tageditor.html.66da263e.js",
    ]:
        assert (target / "assets" / asset).read_text(encoding="utf-8") == f"legacy {asset}"


def test_frontend_source_plan_documents_dist_replacement_gate():
    plan = (ROOT / "docs" / "design" / "frontend-source-of-truth-plan.md").read_text(
        encoding="utf-8"
    )

    for term in [
        "Production Dist Replacement Gate",
        "npm run check",
        "npm run build",
        "npm run smoke",
        "scripts/verify_frontend_source.py --require-built-output",
        "scripts/sync_frontend_source_dist.py",
        "dry-run",
        "Do not manually edit `frontend/dist/`",
        "Do not run `scripts/sync_frontend_source_dist.py --apply`",
    ]:
        assert term in plan


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
        "enable_debug_options",
        "anima_profile_window",
        "anima_nan_check_interval",
        "anima_debug_mode",
        "anima_rope_mismatch_mode",
        "anima_rope_max_seq_tokens",
        "noise_offset",
        "multires_noise_iterations",
        "multires_noise_discount",
        "color_aug",
        "flip_aug",
        "random_crop",
        "seed",
        "clip_skip",
        "ui_custom_params",
        "ddp_timeout",
        "ddp_gradient_as_bucket_view",
        "self_attn_lr",
        "cross_attn_lr",
        "mlp_lr",
        "mod_lr",
        "llm_adapter_lr",
        "lr_scheduler_num_cycles",
        "min_snr_gamma",
        "prodigy_d0",
        "prodigy_d_coef",
        "network_weights",
        "dim_from_weights",
        "scale_weight_norms",
        "train_norm",
        "network_dropout",
        "pissa_init",
        "pissa_method",
        "pissa_niter",
        "pissa_oversample",
        "lokr_factor",
        "full_matrix",
        "tlora_min_rank",
        "tlora_rank_schedule",
        "tlora_orthogonal_init",
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
        "defineTrainingField",
        "defineTrainingRow",
        "defineTrainingSection",
        "defineTrainingSections",
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
    assert "defineTrainingSection<AnimaForm>" in anima_schema
    assert "defineTrainingRow<AnimaForm>" in anima_schema
    assert "defineTrainingSections<AnimaForm>" in anima_schema
    assert "animaModelAssetSection" in anima_schema
    assert "animaDatasetOutputSection" in anima_schema
    assert "animaTrainingSection" in anima_schema
    assert "animaLoraAdapterSection" in anima_schema
    assert "animaParametersSection" in anima_schema
    assert "animaCacheSection" in anima_schema
    assert "animaPreviewSection" in anima_schema
    assert "animaDebugSection" in anima_schema
    assert "animaNoiseSection" in anima_schema
    assert "animaDataEnhancementSection" in anima_schema
    assert "animaOtherSection" in anima_schema
    assert "animaDistributedSection" in anima_schema
    assert "animaSectionsForPlan" in anima_schema
    assert "renderTrainingSchemaSections(animaForm, animaSectionsForPlan(plan))" in anima
    assert 'visibleWhen: { key: "enable_preview", equals: true }' in anima_schema
    assert 'visibleWhen: { key: "weighting_scheme", equals: "logit_normal" }' in anima_schema
    assert 'visibleWhen: { key: "weighting_scheme", equals: "mode" }' in anima_schema
    assert 'visibleWhen: { key: "enable_debug_options", equals: true }' in anima_schema
    assert 'visibleWhen: { key: "lr_scheduler", equals: "cosine_with_restarts" }' in anima_schema
    assert 'visibleWhen: { key: "optimizer_type", equals: "Prodigy" }' in anima_schema
    assert 'visibleWhen: { key: "lora_type", equals: "lokr" }' in anima_schema
    assert 'visibleWhen: { key: "lora_type", equals: "tlora" }' in anima_schema
    assert 'visibleWhen: { key: "pissa_init", equals: true }' in anima_schema
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
        "/",
        "/tensorboard.html",
        "/lora/tools.html",
        "/tageditor.html",
        "/lora/index.html",
        "/lora/basic.html",
        "/lora/master.html",
        "/lora/flux.html",
        "/dreambooth/index.html",
        "/lora/params.html",
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
        "Mature training routes remain compatibility entries",
        "Classic tag editor remains a separate compatibility entry",
        "Source frontend home is owned by frontend/source",
    ]:
        assert term in static_pages
    for route in [
        "/",
        "/tensorboard.html",
        "/lora/tools.html",
        "/tageditor.html",
        "/lora/index.html",
        "/lora/basic.html",
        "/lora/master.html",
        "/lora/flux.html",
        "/dreambooth/index.html",
        "/lora/params.html",
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

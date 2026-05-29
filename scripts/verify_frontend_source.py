#!/usr/bin/env python3
"""Validate the source-owned frontend scaffold.

This intentionally avoids installing npm dependencies.  It checks that the
source project has the route and build contracts needed before the generated
dist can replace the vendored VuePress dist.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REQUIRED_ROUTES = {
    "/",
    "/tagger.html",
    "/tageditor.html",
    "/native-tageditor.html",
    "/dataset-editor.html",
    "/tensorboard.html",
    "/other/settings.html",
    "/lora/index.html",
    "/lora/sd3.html",
    "/lora/basic.html",
    "/lora/master.html",
    "/lora/flux.html",
    "/lora/anima-finetune.html",
    "/lora/params.html",
    "/lora/tools.html",
    "/dreambooth/index.html",
    "/help/guide.html",
    "/other/about.html",
    "/other/changelog.html",
    "/task.html",
}


def load_json(path: Path):
    if not path.is_file():
        raise RuntimeError(f"missing file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def verify_source(root: Path) -> list[dict]:
    source = root / "frontend/source"
    package = load_json(source / "package.json")
    scripts = package.get("scripts", {})
    if "vite build" not in scripts.get("build", ""):
        raise RuntimeError("frontend/source package build script must run vite build")
    if "tsc --noEmit" not in scripts.get("check", ""):
        raise RuntimeError("frontend/source package check script must run TypeScript")
    for dep in ("vite", "vue", "typescript"):
        if dep not in package.get("dependencies", {}):
            raise RuntimeError(f"frontend/source package missing dependency: {dep}")

    vite_config = (source / "vite.config.ts").read_text(encoding="utf-8")
    if "../../build/frontend-source-dist" not in vite_config:
        raise RuntimeError("vite outDir must remain build/frontend-source-dist")

    routes = load_json(source / "src/routes.json")
    paths = [route.get("path") for route in routes]
    if len(paths) != len(set(paths)):
        raise RuntimeError("frontend/source routes contain duplicate paths")
    missing = sorted(REQUIRED_ROUTES - set(paths))
    if missing:
        raise RuntimeError(f"frontend/source routes missing required paths: {missing}")
    for route in routes:
        if not route.get("title") or not route.get("section") or not route.get("description"):
            raise RuntimeError(f"incomplete route entry: {route}")

    alias_script = source / "scripts/write-route-aliases.mjs"
    alias_text = alias_script.read_text(encoding="utf-8")
    if "src/routes.json" not in alias_text or "frontend-source-dist" not in alias_text:
        raise RuntimeError("route alias script must derive output aliases from src/routes.json")

    settings_source = (source / "src/settings.ts").read_text(encoding="utf-8")
    required_settings_terms = [
        "ui-configs",
        "sd-trainer-ui-advanced-links",
        "dataset_tagger_api_endpoint",
        "dataset_tagger_api_key",
        "dataset_tagger_api_model",
        "dataset_tagger_api_prompt",
        'type: "password"',
        "showLegacyTagEditor",
        "showTensorboard",
    ]
    for term in required_settings_terms:
        if term not in settings_source:
            raise RuntimeError(f"settings source missing contract term: {term}")

    main_source = (source / "src/main.ts").read_text(encoding="utf-8")
    anima_source = (source / "src/anima.ts").read_text(encoding="utf-8")
    for term in ("AnimaRoutePage", "isAnimaRoute"):
        if term not in main_source:
            raise RuntimeError(f"main source missing Anima route hook: {term}")

    required_anima_terms = [
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
    ]
    for term in required_anima_terms:
        if term not in anima_source:
            raise RuntimeError(f"Anima source missing route contract term: {term}")

    native_source = (source / "src/nativeTagEditor.ts").read_text(encoding="utf-8")
    native_entry = (source / "src/nativeDatasetEditorMarkup.ts").read_text(
        encoding="utf-8"
    )
    native_runtime = (source / "src/nativeDatasetEditorRuntime.ts").read_text(
        encoding="utf-8"
    )
    native_css = (source / "src/nativeDatasetEditor.css").read_text(
        encoding="utf-8"
    )
    required_native_source_terms = [
        "nativeDatasetEditorMarkup",
        "nativeDatasetEditorRuntime",
        "./nativeDatasetEditor.css",
    ]
    for term in required_native_source_terms:
        if term not in native_source:
            raise RuntimeError(f"native editor source missing contract term: {term}")
    if "sd-native-editor-entry" not in native_source:
        raise RuntimeError("native editor source missing mount id: sd-native-editor-entry")
    if "de-shell-embedded" not in native_entry:
        raise RuntimeError("native editor entry missing contract term: de-shell-embedded")
    if (source / "public/assets/dataset-editor-entry.js").exists():
        raise RuntimeError("native editor entry must be rendered from source, not public assets")
    if "de-shell-embedded" not in native_css:
        raise RuntimeError("native editor CSS missing embedded shell styles")
    if (source / "public/assets/dataset-editor.css").exists():
        raise RuntimeError("native editor CSS must be bundled from source, not public assets")
    if (source / "public/assets/dataset-editor.js").exists():
        raise RuntimeError("native editor runtime must be imported from source, not public assets")
    for term in (
        "/api/dataset-editor/scan",
        "/api/dataset-editor/caption",
        "/api/dataset-editor/batch",
        "/api/dataset-editor/tag",
        "/api/dataset-editor/undo",
        "/api/dataset-editor/redo",
        "dataset_tagger_api_endpoint",
        "dataset_tagger_api_key",
    ):
        if term not in native_runtime:
            raise RuntimeError(f"native editor runtime missing contract term: {term}")

    smoke_script = (source / "scripts/smoke-source-frontend.spec.mjs").read_text(
        encoding="utf-8"
    )
    if "playwright test" not in package.get("scripts", {}).get("smoke", ""):
        raise RuntimeError("frontend/source package missing Playwright smoke script")
    for term in (
        "/native-tageditor.html",
        "/dataset-editor.html",
        "sd-native-editor-entry",
        "/lora/anima-finetune.html",
    ):
        if term not in smoke_script:
            raise RuntimeError(f"browser smoke missing route/assertion term: {term}")

    tagger_source = (source / "src/tagger.ts").read_text(encoding="utf-8")
    for term in (
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
    ):
        if term not in tagger_source:
            raise RuntimeError(f"tagger source missing contract term: {term}")
    if "/assets/tagger-progress.js" in tagger_source:
        raise RuntimeError("tagger source must not depend on vendored tagger-progress.js")
    if (source / "public/assets/tagger-progress.js").exists():
        raise RuntimeError("source frontend should not package tagger-progress.js")
    for term in ("/tagger.html", "sd-tagger-dock"):
        if term not in smoke_script:
            raise RuntimeError(f"browser smoke missing tagger term: {term}")

    return routes


def verify_built_output(root: Path, routes: list[dict]) -> None:
    out = root / "build/frontend-source-dist"
    if not (out / "index.html").is_file():
        raise RuntimeError("build/frontend-source-dist/index.html is missing")
    if not any((out / "assets").glob("*.js")):
        raise RuntimeError("build/frontend-source-dist/assets has no JavaScript bundle")
    if not any((out / "assets").glob("*.css")):
        raise RuntimeError("build/frontend-source-dist/assets has no CSS bundle")
    for route in routes:
        path = route["path"]
        if path == "/":
            continue
        if not (out / path.lstrip("/")).is_file():
            raise RuntimeError(f"built output missing route alias: {path}")
    for asset in (
    ):
        if not (out / asset).is_file():
            raise RuntimeError(f"built output missing native editor asset: {asset}")
    if (out / "assets/dataset-editor-entry.js").exists():
        raise RuntimeError("built output should not include standalone native editor entry")
    if (out / "assets/dataset-editor.css").exists():
        raise RuntimeError("built output should not include standalone native editor CSS")
    if (out / "assets/dataset-editor.js").exists():
        raise RuntimeError("built output should not include standalone native editor runtime")
    if (out / "assets/tagger-progress.js").exists():
        raise RuntimeError("built output should not include vendored tagger-progress.js")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--require-built-output", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    routes = verify_source(root)
    if args.require_built_output:
        verify_built_output(root, routes)
    print(f"frontend source contract OK ({len(routes)} routes)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"frontend source contract failed: {exc}", file=sys.stderr)
        sys.exit(1)

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

#!/usr/bin/env python3
"""Reapply and validate the local frontend/dist patches.

The trainer frontend is a vendored VuePress dist.  Until a source-owned
frontend exists, route/sidebar/page-data edits need to be reproducible instead
of relying on ad hoc minified-bundle edits.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


APP_BUNDLE = Path("frontend/dist/assets/app.547295de.js")
NATIVE_PAGE_DATA = Path("frontend/dist/assets/native-tageditor.html.native.js")
NATIVE_HTML = Path("frontend/dist/native-tageditor.html")
SETTINGS_HTML = Path("frontend/dist/other/settings.html")

SIDEBAR_RE = re.compile(r"const WE=JSON\.parse\(`(?P<json>.*?)`\),x0=")
OLD_NATIVE_ROUTE = (
    '"v-native-tageditor":()=>wt(()=>import("./tageditor.html.66da263e.js"),[]).then(({data:e})=>e)'
)
NEW_NATIVE_ROUTE = (
    '"v-native-tageditor":()=>wt(()=>import("./native-tageditor.html.native.js"),[]).then(({data:e})=>e)'
)
OLD_SETTINGS_ROUTE = (
    '"v-72e1da3e":()=>wt(()=>import("./settings.html.06993f96.js"),[]).then(({data:e})=>e)'
)
NEW_SETTINGS_ROUTE = (
    '"v-72e1da3e":()=>wt(()=>import("./settings.html.06993f96.js?v=dataset-tagger-api"),[]).then(({data:e})=>e)'
)
NATIVE_PAGE_DATA_TEXT = (
    "const e=JSON.parse('{"
    '"key":"v-native-tageditor",'
    '"path":"/native-tageditor.html",'
    '"title":"\\\\u539f\\\\u751f\\\\u6807\\\\u7b7e\\\\u7f16\\\\u8f91",'
    '"lang":"en-US",'
    '"frontmatter":{"type":"native-dataset-editor"},'
    '"excerpt":"",'
    '"headers":[],'
    '"filePathRelative":"native-tageditor.md"'
    "}');export{e as data};\n"
)
NATIVE_NAV_ITEM = (
    '<li><a href="/native-tageditor.html" class="sidebar-item sidebar-heading" '
    'aria-label="原生标签编辑"><!--[--><!--]--> 原生标签编辑 <!--[--><!--]--></a>'
    "<!----><!----></li>"
)


def read_text(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"missing expected frontend asset: {path}")
    return path.read_text(encoding="utf-8")


def write_if_changed(path: Path, text: str, dry_run: bool, changed: list[str]) -> None:
    old = read_text(path) if path.exists() else ""
    if old == text:
        return
    changed.append(str(path))
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def replace_expected(text: str, old: str, new: str, path: Path) -> tuple[str, bool]:
    if new in text:
        return text, False
    if old not in text:
        raise RuntimeError(f"{path}: expected patch target not found")
    return text.replace(old, new, 1), True


def patch_sidebar_json(text: str, path: Path) -> tuple[str, bool]:
    match = SIDEBAR_RE.search(text)
    if not match:
        raise RuntimeError(f"{path}: VuePress sidebar JSON block not found")
    theme = json.loads(match.group("json"))
    sidebar = theme.get("sidebar")
    if not isinstance(sidebar, list):
        raise RuntimeError(f"{path}: theme sidebar is not a list")

    tools = next((item for item in sidebar if item.get("text") == "工具与调试"), None)
    if not tools or not isinstance(tools.get("children"), list):
        raise RuntimeError(f"{path}: tools sidebar group not found")

    children = [
        item
        for item in tools["children"]
        if item.get("link") != "/dataset-editor.html"
        and item.get("text") not in {"标签编辑", "原生标签编辑", "经典标签编辑"}
    ]
    tagger_index = next(
        (idx for idx, item in enumerate(children) if item.get("link") == "/tagger.md"),
        None,
    )
    if tagger_index is None:
        raise RuntimeError(f"{path}: tagger sidebar entry not found")

    insert_at = tagger_index + 1
    children[insert_at:insert_at] = [
        {"text": "经典标签编辑", "link": "/tageditor.md"},
        {"text": "原生标签编辑", "link": "/native-tageditor.html"},
    ]
    tools["children"] = children

    encoded = json.dumps(theme, ensure_ascii=True, separators=(",", ":"))
    json.loads(encoded)
    old = match.group("json")
    if old == encoded:
        return text, False
    return text[: match.start("json")] + encoded + text[match.end("json") :], True


def patch_app_bundle(root: Path, dry_run: bool, changed: list[str]) -> None:
    path = root / APP_BUNDLE
    text = read_text(path)
    text, route_changed = replace_expected(text, OLD_NATIVE_ROUTE, NEW_NATIVE_ROUTE, path)
    text, settings_changed = replace_expected(text, OLD_SETTINGS_ROUTE, NEW_SETTINGS_ROUTE, path)
    text, sidebar_changed = patch_sidebar_json(text, path)
    if route_changed or settings_changed or sidebar_changed:
        write_if_changed(path, text, dry_run, changed)


def patch_native_page_data(root: Path, dry_run: bool, changed: list[str]) -> None:
    path = root / NATIVE_PAGE_DATA
    write_if_changed(path, NATIVE_PAGE_DATA_TEXT, dry_run, changed)


def patch_native_html(root: Path, dry_run: bool, changed: list[str]) -> None:
    path = root / NATIVE_HTML
    text = read_text(path)
    text = text.replace('rel="modulepreload" href="/assets/tageditor.html.66da263e.js"', "")
    text = text.replace('rel="modulepreload" href="/assets/tageditor.html.173f1b6a.js"', "")
    if 'href="/assets/native-tageditor.html.native.js"' not in text:
        app_preload = 'rel="modulepreload" href="/assets/app.547295de.js?v=native-tageditor-nav">'
        if app_preload not in text:
            raise RuntimeError(f"{path}: app modulepreload marker not found")
        text = text.replace(
            app_preload,
            app_preload + '<link rel="modulepreload" href="/assets/native-tageditor.html.native.js">',
            1,
        )
    if "dataset-editor-entry.js" not in text or 'name="sd-dataset-editor-script"' not in text:
        raise RuntimeError(f"{path}: native editor entry script contract is missing")
    write_if_changed(path, text, dry_run, changed)


def patch_settings_html(root: Path, dry_run: bool, changed: list[str]) -> None:
    path = root / SETTINGS_HTML
    text = read_text(path)
    old = "/assets/app.547295de.js"
    new = "/assets/app.547295de.js?v=dataset-tagger-api"
    if new not in text:
        if old not in text:
            raise RuntimeError(f"{path}: app script URL not found")
        text = text.replace(old, new, 1)
    write_if_changed(path, text, dry_run, changed)


def patch_sidebar_html(root: Path, dry_run: bool, changed: list[str]) -> None:
    dist = root / "frontend/dist"
    legacy_re = re.compile(
        r'(<li><a href="/tageditor\.md" class="sidebar-item sidebar-heading" '
        r'aria-label="(?:经典标签编辑|标签编辑)"><!--\[--><!--\]--> (?:经典标签编辑|标签编辑) '
        r'<!--\[--><!--\]--></a><!----><!----></li>)',
        re.DOTALL,
    )
    for path in sorted(dist.rglob("*.html")):
        text = read_text(path)
        if 'href="/tageditor.md"' not in text or 'class="sidebar-items"' not in text:
            continue
        if 'aria-label="标签编辑"' in text:
            text = text.replace('aria-label="标签编辑"', 'aria-label="经典标签编辑"')
            text = text.replace("<!--[--><!--]--> 标签编辑 <!--[--><!--]--></a>", "<!--[--><!--]--> 经典标签编辑 <!--[--><!--]--></a>")
        if 'href="/native-tageditor.html"' not in text:
            text, count = legacy_re.subn(r"\1" + NATIVE_NAV_ITEM, text, count=1)
            if count != 1:
                raise RuntimeError(f"{path}: legacy tag editor sidebar entry not patchable")
        if 'href="/dataset-editor.html"' in text and path.name != "dataset-editor.html":
            raise RuntimeError(f"{path}: dataset editor fallback leaked into trainer sidebar")
        write_if_changed(path, text, dry_run, changed)


def validate(root: Path) -> None:
    app = read_text(root / APP_BUNDLE)
    page = read_text(root / NATIVE_PAGE_DATA)
    native = read_text(root / NATIVE_HTML)
    settings = read_text(root / SETTINGS_HTML)
    match = SIDEBAR_RE.search(app)
    if not match:
        raise RuntimeError("sidebar JSON block missing after patch")
    theme = json.loads(match.group("json"))
    sidebar_text = json.dumps(theme["sidebar"], ensure_ascii=False)
    required = [
        NEW_NATIVE_ROUTE,
        NEW_SETTINGS_ROUTE,
        "/native-tageditor.html",
        "经典标签编辑",
        "原生标签编辑",
    ]
    for needle in required:
        haystack = app if needle.startswith('"v-') else sidebar_text
        if needle not in haystack:
            raise RuntimeError(f"validation failed: {needle!r} missing")
    if '"subtype":"tageditor"' in page or '"type":"native-dataset-editor"' not in page:
        raise RuntimeError("native page data is not native-dataset-editor")
    if 'rel="modulepreload" href="/assets/tageditor.html.66da263e.js"' in native:
        raise RuntimeError("native page still preloads the classic tag editor page data")
    if "dataset-editor-entry.js" not in native:
        raise RuntimeError("native page does not load dataset-editor-entry.js")
    if "/assets/app.547295de.js?v=dataset-tagger-api" not in settings:
        raise RuntimeError("settings HTML does not cache-bust patched app bundle")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--check", action="store_true", help="validate without writing")
    args = parser.parse_args()

    root = args.root.resolve()
    changed: list[str] = []
    patch_app_bundle(root, args.check, changed)
    patch_native_page_data(root, args.check, changed)
    patch_native_html(root, args.check, changed)
    patch_settings_html(root, args.check, changed)
    patch_sidebar_html(root, args.check, changed)
    validate(root)

    if args.check and changed:
        print("frontend/dist patch drift detected:")
        for path in changed:
            print(f"  {path}")
        return 1
    if changed:
        print("patched frontend/dist:")
        for path in changed:
            print(f"  {path}")
    else:
        print("frontend/dist patches already applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Split the legacy Gradio tag editor and native dataset editor entries."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend/dist"
ASSETS = DIST / "assets"

APP_JS = ASSETS / "app.547295de.js"
APP_JS_URL = "/assets/app.547295de.js"
ASSET_VERSION = "20260604-native-tageditor-2"
APP_JS_VERSIONED_URL = f"/assets/app.547295de.js?v={ASSET_VERSION}"
LEGACY_HTML = DIST / "tageditor.html"
NATIVE_HTML = DIST / "native-tageditor.html"
NATIVE_DATA_JS = ASSETS / "native-tageditor.html.native.js"
NATIVE_PAGE_JS = ASSETS / "native-tageditor.html.page.js"

LEGACY_DATA_JS = ASSETS / "tageditor.html.66da263e.js"
LEGACY_PAGE_JS = ASSETS / "tageditor.html.173f1b6a.js"
LEGACY_LABEL = "经典标签编辑"
NATIVE_LABEL = "原生标签编辑"
ORIGINAL_LABEL = "标签编辑"


def strip_native_assets_from_legacy(html: str) -> str:
    html = re.sub(
        r'\s*<link rel="stylesheet" href="/assets/dataset-editor\.css\?v=[^"]+">\s*',
        "\n",
        html,
    )
    html = re.sub(
        r'\s*<meta name="sd-dataset-editor-script" content="/assets/dataset-editor\.js\?v=[^"]+">\s*',
        "\n",
        html,
    )
    html = re.sub(
        r'\s*<script src="/assets/dataset-editor-entry\.js\?v=[^"]+" defer></script>',
        "",
        html,
    )
    return html


def add_native_assets(html: str) -> str:
    if "/assets/dataset-editor.css" not in html:
        html = html.replace(
            '<link rel="stylesheet" href="/assets/style.874872ce.css">',
            '<link rel="stylesheet" href="/assets/style.874872ce.css">\n'
            '    <link rel="stylesheet" href="/assets/dataset-editor.css?v=2.6.0">',
            1,
        )
    if 'name="sd-dataset-editor-script"' not in html:
        html = html.replace(
            "</head>",
            '    <meta name="sd-dataset-editor-script" content="/assets/dataset-editor.js?v=2.6.0">\n'
            "  </head>",
            1,
        )
    if "/assets/dataset-editor-entry.js" not in html:
        html = re.sub(
            r'(<script type="module" src="/assets/app\.547295de\.js(?:\?[^"]*)?" defer></script>)',
            r'<script src="/assets/dataset-editor-entry.js?v=2.6.0" defer></script>\1',
            html,
            count=1,
        )
    return html


def add_native_preloads(html: str) -> str:
    html = html.replace(
        f'<link rel="modulepreload" href="/assets/{LEGACY_PAGE_JS.name}">',
        f'<link rel="modulepreload" href="/assets/{NATIVE_PAGE_JS.name}">',
    )
    html = html.replace(
        f'<link rel="modulepreload" href="/assets/{LEGACY_DATA_JS.name}">',
        f'<link rel="modulepreload" href="/assets/{NATIVE_DATA_JS.name}">',
    )
    html = html.replace(
        f'<link rel="prefetch" href="/assets/{LEGACY_PAGE_JS.name}">',
        f'<link rel="prefetch" href="/assets/{NATIVE_PAGE_JS.name}">',
    )
    native_prefetch = f'<link rel="prefetch" href="/assets/{NATIVE_DATA_JS.name}">'
    if native_prefetch not in html:
        marker = f'<link rel="prefetch" href="/assets/{LEGACY_DATA_JS.name}">'
        if marker in html:
            html = html.replace(marker, marker + native_prefetch, 1)
    return html


def patch_sidebar_html(html: str, active_native: bool) -> str:
    legacy_href = "/tageditor.md"
    native_href = "/native-tageditor.html"

    html = re.sub(
        r'(<a href="/tageditor\.md" class="sidebar-item sidebar-heading)( active)?(" aria-label=")[^"]*(">)'
        r"(?:<!--\[--><!--\]--> )?[^<]*( <!--\[--><!--\]--></a>)",
        lambda m: (
            f"{m.group(1)}{'' if active_native else ' active'}{m.group(3)}{LEGACY_LABEL}{m.group(4)}"
            f"<!--[--><!--]--> {LEGACY_LABEL}{m.group(5)}"
        ),
        html,
    )

    if native_href not in html:
        native_class = (
            "sidebar-item sidebar-heading active"
            if active_native
            else "sidebar-item sidebar-heading"
        )
        native_item = (
            f'<li><a href="{native_href}" class="{native_class}" aria-label="{NATIVE_LABEL}">'
            f"<!--[--><!--]--> {NATIVE_LABEL} <!--[--><!--]--></a><!----><!----></li>"
        )
        html = re.sub(
            r'(<li><a href="/tageditor\.md" class="sidebar-item sidebar-heading(?: active)?" '
            rf'aria-label="{LEGACY_LABEL}">.*?</li>)',
            r"\1" + native_item,
            html,
            count=1,
        )
    else:
        html = re.sub(
            r'(<a href="/native-tageditor\.html" class="sidebar-item sidebar-heading)( active)?(" aria-label=")[^"]*(">)'
            r"(?:<!--\[--><!--\]--> )?[^<]*( <!--\[--><!--\]--></a>)",
            lambda m: (
                f"{m.group(1)}{' active' if active_native else ''}{m.group(3)}{NATIVE_LABEL}{m.group(4)}"
                f"<!--[--><!--]--> {NATIVE_LABEL}{m.group(5)}"
            ),
            html,
        )
    return html


def write_native_data() -> None:
    data = {
        "key": "v-native-tageditor",
        "path": "/native-tageditor.html",
        "title": NATIVE_LABEL,
        "lang": "en-US",
        "frontmatter": {},
        "excerpt": "",
        "headers": [],
        "filePathRelative": "native-tageditor.md",
    }
    compact_data = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    NATIVE_DATA_JS.write_text(
        f"const e=JSON.parse({json.dumps(compact_data, ensure_ascii=False)});export{{e as data}};\n",
        encoding="utf-8",
    )


def write_native_page_component() -> None:
    NATIVE_PAGE_JS.write_text(
        'import{_ as e,o as t,c as r}from"./app.547295de.js?v=20260604-native-tageditor-2";'
        'const c={};function o(_,a){return t(),r("div")}'
        'var s=e(c,[["render",o],["__file","native-tageditor.html.vue"]]);'
        "export{s as default};\n",
        encoding="utf-8",
    )


def patch_html_files() -> None:
    legacy = strip_native_assets_from_legacy(LEGACY_HTML.read_text(encoding="utf-8"))
    legacy = patch_sidebar_html(legacy, active_native=False)
    LEGACY_HTML.write_text(legacy, encoding="utf-8")

    native = add_native_assets(add_native_preloads(legacy))
    native = patch_sidebar_html(native, active_native=True)
    NATIVE_HTML.write_text(native, encoding="utf-8")

    for path in DIST.rglob("*.html"):
        if path in (LEGACY_HTML, NATIVE_HTML):
            continue
        html = path.read_text(encoding="utf-8")
        if 'href="/tageditor.md"' not in html:
            continue
        path.write_text(patch_sidebar_html(html, active_native=False), encoding="utf-8")


def patch_app_cache_buster() -> None:
    for path in DIST.rglob("*.html"):
        html = path.read_text(encoding="utf-8")
        html = re.sub(
            r'href="/assets/app\.547295de\.js(?:\?[^"]*)?"',
            f'href="{APP_JS_VERSIONED_URL}"',
            html,
        )
        html = re.sub(
            r'src="/assets/app\.547295de\.js(?:\?[^"]*)?"',
            f'src="{APP_JS_VERSIONED_URL}"',
            html,
        )
        path.write_text(html, encoding="utf-8")

    for path in ASSETS.glob("*.js"):
        if path == APP_JS:
            continue
        js = path.read_text(encoding="utf-8")
        js = js.replace(
            'from"./app.547295de.js"',
            'from"./app.547295de.js?v=20260604-native-tageditor-2"',
        )
        js = js.replace(
            "from'./app.547295de.js'",
            "from'./app.547295de.js?v=20260604-native-tageditor-2'",
        )
        path.write_text(js, encoding="utf-8")


def patch_app_js() -> None:
    js = APP_JS.read_text(encoding="utf-8")
    js = re.sub(r'import\("\./([^"?]+\.js)\?v=[^"]+"\)', r'import("./\1")', js)
    legacy_component_loader = (
        f'"v-6983ba2a":Jt(()=>wt(()=>import("./{LEGACY_PAGE_JS.name}"),[]))'
    )
    native_component_loader = (
        f'"v-native-tageditor":Jt(()=>wt(()=>import("./{NATIVE_PAGE_JS.name}"),[]))'
    )
    if native_component_loader not in js:
        if legacy_component_loader not in js:
            raise RuntimeError("legacy tageditor component loader not found in app.js")
        js = js.replace(
            legacy_component_loader,
            legacy_component_loader + "," + native_component_loader,
            1,
        )

    legacy_loader = f'"v-6983ba2a":()=>wt(()=>import("./{LEGACY_DATA_JS.name}"),[]).then(({{data:e}})=>e)'
    native_loader = f'"v-native-tageditor":()=>wt(()=>import("./{NATIVE_DATA_JS.name}"),[]).then(({{data:e}})=>e)'
    if native_loader not in js:
        if legacy_loader not in js:
            raise RuntimeError("legacy tageditor loader not found in app.js")
        js = js.replace(legacy_loader, legacy_loader + "," + native_loader, 1)

    legacy_route = (
        '["v-6983ba2a","/tageditor.html",{title:""},["/tageditor","/tageditor.md"]]'
    )
    native_route = f'["v-native-tageditor","/native-tageditor.html",{{title:"{NATIVE_LABEL}"}},["/native-tageditor","/native-tageditor.md"]]'
    legacy_named_native_route = f'["v-native-tageditor","/native-tageditor.html",{{title:"{ORIGINAL_LABEL}"}},["/native-tageditor","/native-tageditor.md"]]'
    js = js.replace(legacy_named_native_route, native_route)
    js = re.sub(
        r'\["v-native-tageditor","/native-tageditor\.html",\{title:"[^"]*"\},\["/native-tageditor","/native-tageditor\.md"\]\]',
        native_route,
        js,
    )
    while js.count(native_route) > 1:
        js = js.replace("," + native_route, "", 1)
    if native_route not in js:
        if legacy_route not in js:
            raise RuntimeError("legacy tageditor route not found in app.js")
        js = js.replace(legacy_route, legacy_route + "," + native_route, 1)

    # Keep the runtime sidebar aligned with the static snapshots.
    replacement = f'{{"text":"{LEGACY_LABEL}","link":"/tageditor.md"}},{{"text":"{NATIVE_LABEL}","link":"/native-tageditor.html"}}'
    js = js.replace(
        f'{{"text":"{ORIGINAL_LABEL}","link":"/tageditor.md"}}', replacement
    )
    js = js.replace('{"text":"鏍囩缂栬緫","link":"/tageditor.md"}', replacement)
    js = js.replace('{"text":"閺嶅洨顒风紓鏍帆","link":"/tageditor.md"}', replacement)
    js = re.sub(
        r'\{"text":"经典标签编辑","link":"/tageditor\.md"\},\{"text":"[^"]*","link":"/native-tageditor\.html"\}',
        replacement,
        js,
    )
    js = re.sub(
        r'import\("\./([^"?]+\.js)"\)',
        rf'import("./\1?v={ASSET_VERSION}")',
        js,
    )
    APP_JS.write_text(js, encoding="utf-8")


def patch_nav_i18n() -> None:
    path = ASSETS / "sd-nav-i18n.js"
    if not path.exists():
        return
    js = path.read_text(encoding="utf-8")
    if f'{NATIVE_LABEL}: "Native Tag Editor"' not in js:
        js = js.replace(
            '标签编辑: "Tag Editor",',
            f'标签编辑: "Tag Editor",\n    {NATIVE_LABEL}: "Native Tag Editor",',
        )
    if f'{LEGACY_LABEL}: "Legacy Tag Editor"' not in js:
        js = js.replace(
            '标签编辑: "Tag Editor",',
            f'标签编辑: "Tag Editor",\n    {LEGACY_LABEL}: "Legacy Tag Editor",',
        )
    path.write_text(js, encoding="utf-8")


def assert_split() -> None:
    legacy = LEGACY_HTML.read_text(encoding="utf-8")
    native = NATIVE_HTML.read_text(encoding="utf-8")
    app = APP_JS.read_text(encoding="utf-8")
    if (
        "dataset-editor-entry.js" in legacy
        or 'name="sd-dataset-editor-script"' in legacy
    ):
        raise RuntimeError("legacy tageditor still contains native editor assets")
    checks = [
        NATIVE_HTML.exists(),
        NATIVE_DATA_JS.exists(),
        NATIVE_PAGE_JS.exists(),
        "dataset-editor-entry.js" in native,
        'name="sd-dataset-editor-script"' in native,
        "v-native-tageditor" in app,
        NATIVE_PAGE_JS.name in app,
        "/native-tageditor.html" in app,
        'href="/native-tageditor.html"' in native,
        APP_JS_VERSIONED_URL in native,
    ]
    if not all(checks):
        raise RuntimeError("native tag editor split incomplete")


def main() -> None:
    write_native_data()
    write_native_page_component()
    patch_html_files()
    patch_app_js()
    patch_app_cache_buster()
    patch_nav_i18n()
    assert_split()
    print("patched native tag editor entry")


if __name__ == "__main__":
    main()

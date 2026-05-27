#!/usr/bin/env python3
"""Add /lora/anima-edit.html training page (trainType anima-edit-lora) to prebuilt frontend."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from guide_html_shared import EDIT_GUIDE_PORTAL_CSS, GUIDE_ANIMA_EDIT_URL

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend/dist"
APP_JS = DIST / "assets/app.547295de.js"
SD3_HTML = DIST / "lora/sd3.html"
POLISH_CSS = DIST / "assets/sd-trainer-ui-polish.css"

ROUTE_KEY = "v-aed1t0ra"
META_JS = DIST / "assets/anima-edit.html.aedmeta.js"
VIEW_JS = DIST / "assets/anima-edit.html.aedview.js"
PAGE_HTML = DIST / "lora/anima-edit.html"

GUIDE_LINK_ESC = GUIDE_ANIMA_EDIT_URL.replace("\\", "\\\\").replace('"', '\\"')

VIEW_JS_CONTENT = (
    'import{_ as s,o as t,c as o,a as e,b as a}from"./app.547295de.js";'
    "const _={},c=e(\"h1\",{id:\"anima-edit-lora-"
    "\\u8BAD\\u7EC3-\\u4E13\\u5BB6\\u6A21\\u5F0F\",tabindex:\"-1\"},"
    "[e(\"a\",{class:\"header-anchor\",href:\"#anima-edit-lora-"
    "\\u8BAD\\u7EC3-\\u4E13\\u5BB6\\u6A21\\u5F0F\",\"aria-hidden\":\"true\"},\"#\"),"
    'a(" Anima Edit LoRA \\u8BAD\\u7EC3 \\u4E13\\u5BB6\\u6A21\\u5F0F")],-1),'
    "n=e(\"p\",null,\"Target + Reference \\u56FE\\u50CF\\u7F16\\u8F91\\u8BAD\\u7EC3\\uFF0C"
    "\\u652F\\u6301\\u5355/\\u53CC\\u53C2\\u8003\\u4E0E sample-prompts.toml \\u9884\\u89C8\\u3002"
    "\\u6587\\u751F\\u56FE LoRA \\u8BF7\\u4F7F\\u7528\\u300CAnima\\u300D\\u9875\\u3002\",-1),"
    "p=e(\"div\",{class:\"sd-edit-guide-portal-wrap\"},["
    'e("a",{class:"sd-edit-guide-portal",href:"' + GUIDE_LINK_ESC + '"},'
    '"\\u67E5\\u770B\\u6570\\u636E\\u96C6\\u76EE\\u5F55\\u793A\\u610F\\u56FE \\u2192"),'
    'e("p",{class:"sd-edit-guide-portal__hint"},'
    '"\\u5355\\u5F20 / \\u53CC\\u5F20\\u53C2\\u8003\\u56FE\\u7684 target \\u4E0E reference \\u600E\\u4E48\\u6446\\uFF1B\\u5728\\u5E2E\\u52A9\\u9875\\u67E5\\u770B\\u793A\\u610F\\u56FE\\u540E\\u56DE\\u6765\\u586B\\u8DEF\\u5F84\\u3002")]),'
    "l=[c,n,p];function i(h,u){return t(),o(\"div\",null,l)}"
    "var m=s(_,[[\"render\",i],[\"__file\",\"anima-edit.html.vue\"]]);export{m as default};"
)

META_JS_CONTENT = (
    "const e=JSON.parse('"
    '{"key":"' + ROUTE_KEY + '",'
    '"path":"/lora/anima-edit.html",'
    '"title":"Anima Edit LoRA \\u8BAD\\u7EC3 \\u4E13\\u5BB6\\u6A21\\u5F0F",'
    '"lang":"en-US",'
    '"frontmatter":{"example":true,"trainType":"anima-edit-lora"},'
    '"excerpt":"","headers":[],"filePathRelative":"lora/anima-edit.md"}'
    "');export{e as data};"
)

B2_ENTRY = (
    f'"{ROUTE_KEY}":()=>wt(()=>import("./anima-edit.html.aedmeta.js"),[]).then(({{data:e}})=>e),'
)

VIEW_ENTRY = (
    f'"{ROUTE_KEY}":Jt(()=>wt(()=>import("./anima-edit.html.aedview.js"),[])),'
)

ROUTE_ENTRY = (
    f'["{ROUTE_KEY}","/lora/anima-edit.html",'
    '{"title":"Anima Edit LoRA \\u8BAD\\u7EC3 \\u4E13\\u5BB6\\u6A21\\u5F0F"},'
    '["/lora/anima-edit","/lora/anima-edit.md"]],'
)

SIDEBAR_INSERT = (
    '{"text":"Anima","link":"/lora/sd3.md"},'
    '{"text":"Anima Edit","link":"/lora/anima-edit.md"},'
)

OLD_SIDEBAR_LABEL = '{"text":"Anima \\u56FE\\u50CF\\u7F16\\u8F91","link":"/lora/anima-edit.md"},'

EXPERT_MAIN_HTML = (
    '<main><div><h1 id="anima-edit-lora-训练-专家模式" tabindex="-1">'
    '<a class="header-anchor" href="#anima-edit-lora-训练-专家模式" aria-hidden="true">#</a> '
    "Anima Edit LoRA</h1>"
    "<p>Target + Reference 图像编辑训练 专家模式</p>"
    '<div class="sd-edit-guide-portal-wrap">'
    f'<a class="sd-edit-guide-portal" href="{GUIDE_ANIMA_EDIT_URL}">查看数据集目录示意图 →</a>'
    '<p class="sd-edit-guide-portal__hint">单张 / 双张参考图的 target 与 reference 怎么摆；在帮助页查看示意图后回来填路径。</p>'
    "</div></div></main>"
)


def patch_portal_css() -> None:
    css = POLISH_CSS.read_text(encoding="utf-8")
    marker = "/* Anima Edit 专家区 → 帮助页数据集说明 */"
    if marker in css:
        start = css.find(marker)
        end = css.find("\n/* ", start + 1)
        if end < 0:
            end = len(css)
        css = css[:start] + EDIT_GUIDE_PORTAL_CSS.strip() + "\n" + css[end:]
    else:
        css = css.rstrip() + "\n" + EDIT_GUIDE_PORTAL_CSS
    POLISH_CSS.write_text(css, encoding="utf-8")
    style = DIST / "assets/style.874872ce.css"
    if style.exists():
        t = style.read_text(encoding="utf-8")
        s = t.find("/* ========== SD-Trainer UI polish")
        if s >= 0:
            style.write_text(t[:s] + css, encoding="utf-8")
    print("patched portal css")


def build_page_html() -> str:
    html = SD3_HTML.read_text(encoding="utf-8")
    html = html.replace(
        '<title>Anima Stable Diffusion LoRA | SD 训练 UI</title>',
        '<title>Anima Edit LoRA | SD 训练 UI</title>',
    )
    html = html.replace(
        '<link rel="modulepreload" href="/assets/sd3.html.1a4bf31e.js">'
        '<link rel="modulepreload" href="/assets/sd3.html.eaeb05e1.js">',
        '<link rel="modulepreload" href="/assets/anima-edit.html.aedview.js">'
        '<link rel="modulepreload" href="/assets/anima-edit.html.aedmeta.js">',
    )
    html = html.replace(
        '<h1 id="sd3-训练-专家模式"',
        '<h1 id="anima-edit-lora-训练-专家模式"',
    )
    html = html.replace(
        'href="#sd3-训练-专家模式"',
        'href="#anima-edit-lora-训练-专家模式"',
    )
    html = re.sub(
        r">[^<]*</h1>",
        "> Anima Edit LoRA</h1>",
        html,
        count=1,
    )
    html = re.sub(
        r"<main><div><h1[^>]*>.*?</h1>.*?</div></main>",
        EXPERT_MAIN_HTML,
        html,
        count=1,
        flags=re.DOTALL,
    )
    return html


def patch_app_js(js: str) -> str:
    already = ROUTE_KEY in js
    if already:
        print("app.js already has anima-edit route (will still ensure view map)")
    if B2_ENTRY not in js and not already:
        anchor = '"v-0dc76a3b":()=>wt(()=>import("./sd3.html.eaeb05e1.js"),[]).then(({data:e})=>e),'
        if anchor not in js:
            raise SystemExit("b2 anchor for sd3 not found")
        js = js.replace(anchor, anchor + B2_ENTRY, 1)
    if not already:
        route_anchor = (
            '["v-0dc76a3b","/lora/sd3.html",{title:"SD3 \\u8BAD\\u7EC3 \\u4E13\\u5BB6\\u6A21\\u5F0F"},'
            '["/lora/sd3","/lora/sd3.md"]],'
        )
        if route_anchor not in js:
            raise SystemExit("route anchor for sd3 not found")
        js = js.replace(route_anchor, route_anchor + ROUTE_ENTRY, 1)
    view_anchor = '"v-0dc76a3b":Jt(()=>wt(()=>import("./sd3.html.1a4bf31e.js"),[])),'
    if VIEW_ENTRY not in js:
        if view_anchor not in js:
            raise SystemExit("view component anchor for sd3 not found")
        js = js.replace(view_anchor, view_anchor + VIEW_ENTRY, 1)
    old_sidebar = '{"text":"Anima","link":"/lora/sd3.md"},'
    if SIDEBAR_INSERT not in js:
        if OLD_SIDEBAR_LABEL in js:
            js = js.replace(OLD_SIDEBAR_LABEL, '{"text":"Anima Edit","link":"/lora/anima-edit.md"},')
        elif old_sidebar in js:
            js = js.replace(old_sidebar, SIDEBAR_INSERT, 1)
    else:
        js = js.replace(OLD_SIDEBAR_LABEL, '{"text":"Anima Edit","link":"/lora/anima-edit.md"},')
    return js


def main() -> None:
    META_JS.write_text(META_JS_CONTENT, encoding="utf-8")
    VIEW_JS.write_text(VIEW_JS_CONTENT, encoding="utf-8")
    print(f"wrote {META_JS.relative_to(ROOT)}")
    print(f"wrote {VIEW_JS.relative_to(ROOT)}")

    PAGE_HTML.write_text(build_page_html(), encoding="utf-8")
    print(f"wrote {PAGE_HTML.relative_to(ROOT)}")

    js = APP_JS.read_text(encoding="utf-8")
    APP_JS.write_text(patch_app_js(js), encoding="utf-8")
    print(f"patched {APP_JS.relative_to(ROOT)}")

    patch_portal_css()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Add /lora/anima-edit.html training page (trainType anima-edit-lora) to prebuilt frontend."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend/dist"
APP_JS = DIST / "assets/app.547295de.js"
SD3_HTML = DIST / "lora/sd3.html"

ROUTE_KEY = "v-aed1t0ra"
META_JS = DIST / "assets/anima-edit.html.aedmeta.js"
VIEW_JS = DIST / "assets/anima-edit.html.aedview.js"
PAGE_HTML = DIST / "lora/anima-edit.html"

VIEW_JS_CONTENT = (
    'import{_ as s,o as t,c as o,a as e,b as a}from"./app.547295de.js";'
    "const _={},c=e(\"h1\",{id:\"anima-edit-lora-"
    "\\u8BAD\\u7EC3-\\u4E13\\u5BB6\\u6A21\\u5F0F\",tabindex:\"-1\"},"
    "[e(\"a\",{class:\"header-anchor\",href:\"#anima-edit-lora-"
    "\\u8BAD\\u7EC3-\\u4E13\\u5BB6\\u6A21\\u5F0F\",\"aria-hidden\":\"true\"},\"#\"),"
    "a(\" Anima \\u56FE\\u50CF\\u7F16\\u8F91 LoRA \\u8BAD\\u7EC3 \\u4E13\\u5BB6\\u6A21\\u5F0F\")],-1),"
    "n=e(\"p\",null,\"Target + Reference \\u56FE\\u50CF\\u7F16\\u8F91\\u8BAD\\u7EC3\\uFF0C"
    "\\u652F\\u6301\\u53CC\\u53C2\\u8003\\u4E0E sample-prompts.toml \\u9884\\u89C8\",-1),"
    "d=e(\"p\",null,\"\\u6570\\u636E\\u96C6\\uFF1Atarget/ + reference/<stem>/ \\u4E0B 2 \\u5F20\\u53C2\\u8003\\u56FE\\u3002"
    "\\u6587\\u751F\\u56FE LoRA \\u8BF7\\u4F7F\\u7528\\u300CAnima\\u300D\\u9875\\u3002\",-1),"
    "l=[c,n,d];function i(h,u){return t(),o(\"div\",null,l)}"
    "var p=s(_,[[\"render\",i],[\"__file\",\"anima-edit.html.vue\"]]);export{p as default};"
)

META_JS_CONTENT = (
    "const e=JSON.parse('"
    '{"key":"' + ROUTE_KEY + '",'
    '"path":"/lora/anima-edit.html",'
    '"title":"Anima \\u56FE\\u50CF\\u7F16\\u8F91 LoRA \\u8BAD\\u7EC3 \\u4E13\\u5BB6\\u6A21\\u5F0F",'
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
    '{"title":"Anima \\u56FE\\u50CF\\u7F16\\u8F91 LoRA \\u8BAD\\u7EC3 \\u4E13\\u5BB6\\u6A21\\u5F0F"},'
    '["/lora/anima-edit","/lora/anima-edit.md"]],'
)

SIDEBAR_INSERT = (
    '{"text":"Anima","link":"/lora/sd3.md"},'
    '{"text":"Anima \\u56FE\\u50CF\\u7F16\\u8F91","link":"/lora/anima-edit.md"},'
)


def build_page_html() -> str:
    html = SD3_HTML.read_text(encoding="utf-8")
    html = html.replace(
        '<title>Anima Stable Diffusion LoRA | SD 训练 UI</title>',
        '<title>Anima 图像编辑 LoRA | SD 训练 UI</title>',
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
        "> Anima 图像编辑 LoRA</h1>",
        html,
        count=1,
    )
    html = re.sub(
        r"<main><div><h1[^>]*>.*?</h1><p>.*?</p><p>.*?</p></div></main>",
        "<main><div><h1 id=\"anima-edit-lora-训练-专家模式\" tabindex=\"-1\">"
        "<a class=\"header-anchor\" href=\"#anima-edit-lora-训练-专家模式\" aria-hidden=\"true\">#</a> "
        "Anima 图像编辑 LoRA</h1>"
        "<p>Target + Reference 图像编辑训练 专家模式</p>"
        "<p>双参考图编辑训练；预览写入 sample-prompts.toml manifest。文生图 LoRA 请使用侧栏「Anima」页。</p>"
        "</div></main>",
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
    if old_sidebar in js and SIDEBAR_INSERT not in js:
        js = js.replace(old_sidebar, SIDEBAR_INSERT, 1)
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


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Add Anima full finetune training page to frontend/dist (VuePress artifacts)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend" / "dist"
ASSETS = DIST / "assets"
APP_JS = ASSETS / "app.547295de.js"

ROUTE_KEY = "v-a1f1ne2e"
DATA_JS = ASSETS / "anima-finetune.html.eaeb05f2.js"
COMP_JS = ASSETS / "anima-finetune.html.1a4bf32e.js"
HTML_PATH = DIST / "lora" / "anima-finetune.html"

SIDEBAR_SNIPPET = '{"text":"Anima 全量","link":"/lora/anima-finetune.md"},'


def patch_app_js() -> None:
    text = APP_JS.read_text(encoding="utf-8")
    if ROUTE_KEY in text:
        print("app.js already has anima-finetune route")
        return

    import_marker = 'import("./sd3.html.eaeb05e1.js"),[]).then(({data:e})=>e),'
    route_import = (
        'import("./sd3.html.eaeb05e1.js"),[]).then(({data:e})=>e),'
        f'"{ROUTE_KEY}":()=>wt(()=>import("./anima-finetune.html.eaeb05f2.js"),[]).then(({{data:e}})=>e),'
    )
    if import_marker not in text:
        raise SystemExit("sd3 import marker not found in app.js")
    text = text.replace(import_marker, route_import, 1)

    route_tuple = (
        '["v-0dc76a3b","/lora/sd3.html",{title:"SD3 \\u8BAD\\u7EC3 \\u4E13\\u5BB6\\u6A21\\u5F0F"},["/lora/sd3","/lora/sd3.md"]],'
    )
    finetune_tuple = (
        '["v-0dc76a3b","/lora/sd3.html",{title:"SD3 \\u8BAD\\u7EC3 \\u4E13\\u5BB6\\u6A21\\u5F0F"},["/lora/sd3","/lora/sd3.md"]],'
        f'["{ROUTE_KEY}","/lora/anima-finetune.html",{{title:"Anima \\u5168\\u91cf\\u5FAE\\u8C03 \\u4E13\\u5BB6\\u6A21\\u5F0F"}},["/lora/anima-finetune","/lora/anima-finetune.md"]],'
    )
    if route_tuple not in text:
        raise SystemExit("sd3 route tuple not found in app.js")
    text = text.replace(route_tuple, finetune_tuple, 1)

    if SIDEBAR_SNIPPET.replace("\\u5168\\u91cf", "全量") in text or "anima-finetune.md" in text:
        pass
    elif '"Anima","link":"/lora/sd3.md"' in text:
        text = text.replace(
            '"Anima","link":"/lora/sd3.md"}',
            '"Anima","link":"/lora/sd3.md"},' + SIDEBAR_SNIPPET.rstrip(",") + "}",
            1,
        )
    APP_JS.write_text(text, encoding="utf-8")
    print("patched app.js")


def write_page_assets() -> None:
    data = {
        "key": ROUTE_KEY,
        "path": "/lora/anima-finetune.html",
        "title": "Anima 全量微调 专家模式",
        "lang": "en-US",
        "frontmatter": {"example": True, "trainType": "anima-finetune"},
        "excerpt": "",
        "headers": [],
        "filePathRelative": "lora/anima-finetune.md",
    }
    DATA_JS.write_text(
        f"const e=JSON.parse({json.dumps(json.dumps(data, ensure_ascii=False))});export{{e as data}};",
        encoding="utf-8",
    )
    COMP_JS.write_text(
        'import{_ as s,o as t,c as o,a as e,b as a}from"./app.547295de.js";'
        "const _={},"
        'c=e("h1",{id:"anima-finetune",tabindex:"-1"},['
        'e("a",{class:"header-anchor",href:"#anima-finetune","aria-hidden":"true"},"#"),'
        'a(" Anima 全量微调 专家模式")],-1),'
        'n=e("p",null,"Anima DiT 全量微调（full finetune），更新完整 transformer 权重",-1),'
        'd=e("p",null,"使用 Qwen3 + T5 + anima_train.py；显存需求显著高于 LoRA",-1),'
        "l=[c,n,d];"
        "function i(h,u){return t(),o(\"div\",null,l)}"
        'var p=s(_,[["render",i],["__file","anima-finetune.html.vue"]]);export{p as default};',
        encoding="utf-8",
    )

    src = DIST / "lora" / "sd3.html"
    html = src.read_text(encoding="utf-8")
    html = html.replace("/lora/sd3.html", "/lora/anima-finetune.html")
    html = html.replace("sd3.html.1a4bf31e.js", "anima-finetune.html.1a4bf32e.js")
    html = html.replace("sd3.html.eaeb05e1.js", "anima-finetune.html.eaeb05f2.js")
    html = re.sub(
        r"<title>[^<]*</title>",
        "<title>Anima 全量微调 | SD 训练 UI</title>",
        html,
        count=1,
    )
    html = re.sub(
        r"<h1[^>]*>.*?</h1>",
        '<h1 id="anima-finetune" tabindex="-1"><a class="header-anchor" href="#anima-finetune" aria-hidden="true">#</a> Anima 全量微调</h1>',
        html,
        count=1,
        flags=re.DOTALL,
    )
    html = re.sub(
        r"<p>Anima DiT 模型 LoRA.*?</p>",
        "<p>Anima DiT 全量微调（full finetune）</p>",
        html,
        count=1,
    )
    html = re.sub(
        r"<p>Anima DiT 训练入口.*?</p>",
        "<p>对接上游 anima_train.py，适合小数据集风格化/角色定制（高显存）</p>",
        html,
        count=1,
    )
    HTML_PATH.write_text(html, encoding="utf-8")
    print("wrote lora/anima-finetune.html + assets")


def patch_home_portal() -> None:
    index_js = ASSETS / "index.html.c6ef684b.js"
    if not index_js.exists():
        return
    text = index_js.read_text(encoding="utf-8")
    needle = 'href="/lora/sd3.html"><span class="sd-home-portal__title">Anima</span>'
    insert = (
        'href="/lora/sd3.html"><span class="sd-home-portal__title">Anima LoRA</span>'
    )
    if insert in text:
        text = text.replace(needle, insert, 1)
    finetune = (
        '<a class="sd-home-portal" href="/lora/anima-finetune.html">'
        '<span class="sd-home-portal__title">Anima 全量</span>'
        '<span class="sd-home-portal__desc">DiT full finetune</span></a>'
    )
    if "anima-finetune.html" not in text and 'href="/lora/flux.html"' in text:
        text = text.replace(
            '<a class="sd-home-portal" href="/lora/flux.html">',
            finetune + '<a class="sd-home-portal" href="/lora/flux.html">',
            1,
        )
        index_js.write_text(text, encoding="utf-8")
        print("patched home portal")


def run_sidebar_patch() -> None:
    nav = ROOT / "scripts" / "patch-sidebar-nav.py"
    nav_text = nav.read_text(encoding="utf-8")
    if "anima-finetune.md" not in nav_text:
        nav_text = nav_text.replace(
            '{"text":"Anima","link":"/lora/sd3.md"},',
            '{"text":"Anima LoRA","link":"/lora/sd3.md"},\n    '
            '{"text":"Anima 全量","link":"/lora/anima-finetune.md"},',
            1,
        )
        nav.write_text(nav_text, encoding="utf-8")
    subprocess.run([sys.executable, str(nav)], cwd=ROOT, check=True)


def main() -> None:
    write_page_assets()
    patch_app_js()
    patch_home_portal()
    run_sidebar_patch()
    print("anima-finetune UI patch done")


if __name__ == "__main__":
    main()

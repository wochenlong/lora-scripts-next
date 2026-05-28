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
POLISH_CSS = ASSETS / "sd-trainer-ui-polish.css"
STYLE_CSS = ASSETS / "style.874872ce.css"

ROUTE_KEY = "v-a1f1ne2e"
COMP_IMPORT = '"v-a1f1ne2e":Jt(()=>wt(()=>import("./anima-finetune.html.1a4bf32e.js"),[])),'
I0_SD3_MARKER = '"v-0dc76a3b":Jt(()=>wt(()=>import("./sd3.html.1a4bf31e.js"),[])),'
TAGLINE_TEXT = "anima-finetune ，一切皆有可能"
FINETUNE_DESC = "更新完整 DiT 权重，适合进阶玩家训练，需充足样本与高显存"
TAGLINE_CSS_MARKER = "sd-anima-finetune-tagline"
DATA_JS = ASSETS / "anima-finetune.html.eaeb05f2.js"
COMP_JS = ASSETS / "anima-finetune.html.1a4bf32e.js"
HTML_PATH = DIST / "lora" / "anima-finetune.html"

SIDEBAR_SNIPPET = '{"text":"Anima Finetune","link":"/lora/anima-finetune.md"},'


def patch_app_js() -> None:
    text = APP_JS.read_text(encoding="utf-8")
    if COMP_IMPORT in text:
        print("app.js already has anima-finetune page component (i0)")
    elif I0_SD3_MARKER in text:
        text = text.replace(I0_SD3_MARKER, I0_SD3_MARKER + COMP_IMPORT, 1)
        print("patched app.js i0 page component map")
    else:
        raise SystemExit("sd3 i0 import marker not found in app.js")

    if ROUTE_KEY in text and f'"{ROUTE_KEY}","/lora/anima-finetune.html"' in text:
        APP_JS.write_text(text, encoding="utf-8")
        print("app.js route/data already present")
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
    elif '"全量微调"' in text and "anima-finetune.md" not in text:
        text = text.replace(
            '{"text":"\\u5168\\u91cf\\u5fae\\u8c03","link":"/dreambooth/index.md","collapsible":false,"children":['
            '{"text":"Stable Diffusion","link":"/dreambooth/index.md"},',
            '{"text":"\\u5168\\u91cf\\u5fae\\u8c03","link":"/lora/anima-finetune.md","collapsible":false,"children":['
            + SIDEBAR_SNIPPET
            + '{"text":"Stable Diffusion","link":"/dreambooth/index.md"},',
            1,
        )
    APP_JS.write_text(text, encoding="utf-8")
    print("patched app.js")


def write_page_assets() -> None:
    data = {
        "key": ROUTE_KEY,
        "path": "/lora/anima-finetune.html",
        "title": "Anima Finetune 专家模式",
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
        f'f=e("p",{{class:"sd-anima-finetune-tagline"}},{json.dumps(TAGLINE_TEXT)},-1),'
        'c=e("h1",{id:"anima-finetune",tabindex:"-1"},['
        'e("a",{class:"header-anchor",href:"#anima-finetune","aria-hidden":"true"},"#"),'
        'a(" Anima Finetune 专家模式")],-1),'
        'n=e("p",null,"Anima DiT 全量微调（full finetune）",-1),'
        f'd=e("p",null,{json.dumps(FINETUNE_DESC)},-1),'
        "l=[f,c,n,d];"
        'function i(h,u){return t(),o("div",null,l)}'
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
        "<title>Anima Finetune | SD 训练 UI</title>",
        html,
        count=1,
    )
    tagline_html = f'<p class="sd-anima-finetune-tagline">{TAGLINE_TEXT}</p>'
    html = re.sub(
        r"<h1[^>]*>.*?</h1>",
        tagline_html
        + '<h1 id="anima-finetune" tabindex="-1"><a class="header-anchor" href="#anima-finetune" aria-hidden="true">#</a> Anima Finetune</h1>',
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
        f"<p>{FINETUNE_DESC}</p>",
        html,
        count=1,
    )
    HTML_PATH.write_text(html, encoding="utf-8")
    print("wrote lora/anima-finetune.html + assets")


def append_tagline_css() -> None:
    if not POLISH_CSS.exists():
        return
    css = POLISH_CSS.read_text(encoding="utf-8")
    if TAGLINE_CSS_MARKER in css:
        print("tagline css already present")
        return
    block = """

/* ----- Anima Finetune：右栏右上角标语 ----- */
.example-container > .right-container .theme-default-content main > div {
  position: relative;
  padding-top: 2.25rem;
}

.example-container > .right-container .sd-anima-finetune-tagline {
  position: absolute;
  top: 0;
  right: 0;
  margin: 0;
  max-width: 100%;
  padding: 0.35rem 0.7rem;
  border-radius: var(--sd-radius-pill, 999px);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
  line-height: 1.45;
  text-align: right;
  color: var(--el-color-primary, #409eff);
  background: color-mix(in srgb, var(--el-color-primary, #409eff) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--el-color-primary, #409eff) 24%, transparent);
  pointer-events: none;
  user-select: none;
}

html.dark .example-container > .right-container .sd-anima-finetune-tagline {
  background: color-mix(in srgb, var(--el-color-primary, #409eff) 16%, transparent);
}
"""
    POLISH_CSS.write_text(css.rstrip() + block + "\n", encoding="utf-8")
    if STYLE_CSS.exists():
        style = STYLE_CSS.read_text(encoding="utf-8")
        if TAGLINE_CSS_MARKER not in style:
            STYLE_CSS.write_text(style.rstrip() + block + "\n", encoding="utf-8")
            print("appended anima-finetune tagline css to style bundle")
    print("appended anima-finetune tagline css")


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
        '<span class="sd-home-portal__title">Anima Finetune</span>'
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
    subprocess.run([sys.executable, str(ROOT / "scripts" / "patch-sidebar-nav.py")], cwd=ROOT, check=True)


def main() -> None:
    write_page_assets()
    patch_app_js()
    append_tagline_css()
    patch_home_portal()
    run_sidebar_patch()
    print("anima-finetune UI patch done")


if __name__ == "__main__":
    main()

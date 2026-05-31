#!/usr/bin/env python3
"""Home hub (portals) + help/guide page + Next Trainer branding."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend/dist"
ASSETS = DIST / "assets"
APP_JS = ASSETS / "app.547295de.js"
INDEX_JS = ASSETS / "index.html.c6ef684b.js"
INDEX_HTML = DIST / "index.html"
INDEX_META = ASSETS / "index.html.ec4ace46.js"
GUIDE_HTML = DIST / "help/guide.html"
GUIDE_DATA_JS = ASSETS / "guide.html.b8e2d701.js"
GUIDE_COMP_JS = ASSETS / "guide.html.c3f4a902.js"
PATCH_NAV = ROOT / "scripts/patch-sidebar-nav.py"

GUIDE_KEY = "v-b8e2d701"
MONITOR_URL = "/train-monitor"
MONITOR_DESC = "自动端口 · 实时日志"

BADGES = """<p class="sd-home-badges" align="center"><a href="https://github.com/wochenlong/lora-scripts-next" style="margin:2px;"><img alt="GitHub Repo stars" src="https://img.shields.io/github/stars/wochenlong/lora-scripts-next"></a><a href="https://github.com/wochenlong/lora-scripts-next" style="margin:2px;"><img alt="GitHub forks" src="https://img.shields.io/github/forks/wochenlong/lora-scripts-next"></a><a href="https://raw.githubusercontent.com/wochenlong/lora-scripts-next/master/LICENSE" style="margin:2px;"><img src="https://img.shields.io/github/license/wochenlong/lora-scripts-next" alt="license"></a><a href="https://github.com/wochenlong/lora-scripts-next/releases" style="margin:2px;"><img src="https://img.shields.io/github/v/release/wochenlong/lora-scripts-next?color=blueviolet&amp;include_prereleases" alt="release"></a></p>"""

HOME_HUB_HTML = f"""<div class="sd-home-hub">{BADGES}<p class="sd-home-lead"><strong>lora-scripts-next</strong>（Next Trainer）是基于秋叶 <a href="https://github.com/Akegarasu/lora-scripts" target="_blank" rel="noopener noreferrer">lora-scripts</a> 的<strong>下一代</strong> Stable Diffusion 训练 WebUI：在浏览器里配参数、一键开训。</p><h2 class="sd-home-section-title">LoRA 训练</h2><div class="sd-home-portals"><a class="sd-home-portal sd-home-portal--primary" href="/lora/sd3.html"><span class="sd-home-portal__title">Anima LoRA</span><span class="sd-home-portal__desc">DiT · 主推</span></a><a class="sd-home-portal" href="/lora/anima-fast.html"><span class="sd-home-portal__title">Anima Fast</span><span class="sd-home-portal__desc">插件加速 · 进阶</span></a><a class="sd-home-portal" href="/lora/flux.html"><span class="sd-home-portal__title">Flux</span><span class="sd-home-portal__desc">Flux LoRA</span></a><a class="sd-home-portal" href="/lora/master.html"><span class="sd-home-portal__title">Stable Diffusion</span><span class="sd-home-portal__desc">SD1.5 / SDXL LoRA</span></a></div><h2 class="sd-home-section-title">全量微调</h2><div class="sd-home-portals"><a class="sd-home-portal" href="/lora/anima-finetune.html"><span class="sd-home-portal__title">Anima Finetune</span><span class="sd-home-portal__desc">DiT full finetune · 高显存</span></a><a class="sd-home-portal" href="/dreambooth/index.html"><span class="sd-home-portal__title">Stable Diffusion</span><span class="sd-home-portal__desc">SDXL Finetune · Dreambooth</span></a></div><h2 class="sd-home-section-title">训练监控</h2><div class="sd-home-portals sd-home-portals--single"><a class="sd-home-portal sd-home-portal--monitor" href="{MONITOR_URL}" target="_blank" rel="noopener noreferrer"><span class="sd-home-portal__title">训练监控</span><span class="sd-home-portal__desc">{MONITOR_DESC}</span></a></div><p class="sd-home-foot">详细步骤见 <a href="/help/guide.html">帮助 → 新手上路</a>；秋叶用户迁移说明也在该页。参数释义 · <a href="/lora/params.html">训练参数说明</a> · <a href="/other/changelog.html">更新日志</a></p></div>"""

# Keep in sync with scripts/patch-brand-illustrations.py GUIDE_BODY
GUIDE_HTML_BODY = """<div class="sd-guide"><div class="sd-guide-intro"><div class="sd-guide-intro__art" aria-hidden="true"><img src="/assets/guide-mascot.webp?v=20260525-nt5" alt="" loading="lazy" decoding="async"></div><div class="sd-guide-intro__body"><h2 id="新手上路" tabindex="-1"><a class="header-anchor" href="#新手上路" aria-hidden="true">#</a> 新手上路</h2><ol><li><strong>准备数据</strong>：训练图片 + 同名 <code>.txt</code> 标签；可用「工具与调试 → 数据集打标」。</li><li><strong>选择训练类型</strong>（侧栏「训练」）：<ul><li><strong>LoRA 训练</strong><ul><li><a href="/lora/sd3.html">Anima LoRA</a> — Anima DiT（推荐）</li><li><a href="/lora/anima-fast.html">Anima Fast</a> — 可选插件加速（进阶，页内安装）</li><li><a href="/lora/flux.html">Flux</a></li><li><a href="/lora/master.html">Stable Diffusion</a> — SD1.5 / SDXL LoRA</li></ul></li><li><strong>全量微调</strong><ul><li><a href="/lora/anima-finetune.html">Anima Finetune</a> — DiT 整模微调（高显存）</li><li><a href="/dreambooth/index.html">Stable Diffusion</a> — 默认 SDXL Finetune，可切换 SD1.5 Dreambooth</li></ul></li></ul></li><li><strong>填写参数并开训</strong>：中栏表单 → 右栏「开始训练」。</li><li><strong>查看进度</strong>：<a href="/train-monitor" target="_blank" rel="noopener noreferrer">训练监控</a>、<a href="/tensorboard.html">Tensorboard</a>。</li></ol></div></div><section class="sd-guide-migrate"><h2 id="从秋叶版迁移" tabindex="-1"><a class="header-anchor" href="#从秋叶版迁移" aria-hidden="true">#</a> 从秋叶版迁移</h2><p>若你使用过 <strong>Akegarasu/lora-scripts</strong>（秋叶一键包），本版主要变化：</p><ul><li><strong>品牌</strong>：项目名 <strong>lora-scripts-next</strong> / Next Trainer，侧栏按「训练 / 工具 / 帮助 / 其他」分组。</li><li><strong>导航</strong>：LoRA 与全量微调分栏；原「新手 / 专家」不再平铺（SD1.5 精简页：<a href="/lora/basic.html">/lora/basic.html</a>）。</li><li><strong>Anima</strong>：LoRA 与 Finetune 分入口（Qwen + T5 + DiT）。</li><li><strong>监控</strong>：独立 <a href="/train-monitor" target="_blank" rel="noopener noreferrer">训练监控页</a>、Loss 曲线、<code>/train-log</code> 日志流。</li><li>更多版本说明见 <a href="/other/changelog.html">更新日志</a>。</li></ul></section></div>"""


def patch_index_js() -> None:
    text = INDEX_JS.read_text(encoding="utf-8")
    text = text.replace('id:"sd-trainer"', 'id:"next-trainer"')
    text = text.replace('href:"#sd-trainer"', 'href:"#next-trainer"')
    text = text.replace(" SD-Trainer", " Next Trainer", 1)
    text = text.replace('alt:"SD-Trainer"', 'alt:"Next Trainer"')
    text = text.replace(
        'E=s("p",null,"Stable Diffusion \\u8BAD\\u7EC3 UI v2.3.0",-1)',
        'E=s("p",null,"lora-scripts-next \\u00b7 \\u4e0b\\u4e00\\u4ee3\\u8bad\\u7ec3 WebUI",-1)',
    )
    start = text.find("h=r(`")
    end = text.find("`,10);function F")
    if start < 0 or end < 0:
        raise SystemExit("index template not found")
    text = text[: start + len("h=r(`")] + HOME_HUB_HTML + text[end:]
    INDEX_JS.write_text(text, encoding="utf-8")
    print("patched index.js")


def patch_index_ssr() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    html = html.replace('id="sd-trainer"', 'id="next-trainer"')
    html = html.replace("#sd-trainer", "#next-trainer")
    html = re.sub(
        r"<h1[^>]*>.*?SD-Trainer.*?</h1>",
        '<h1 id="next-trainer" tabindex="-1"><a class="header-anchor" href="#next-trainer" aria-hidden="true">#</a> Next Trainer</h1>',
        html,
        count=1,
        flags=re.DOTALL,
    )
    html = html.replace(
        "Stable Diffusion 训练 UI v2.3.0",
        "lora-scripts-next · 下一代训练 WebUI",
    )
    html = html.replace('alt="SD-Trainer"', 'alt="Next Trainer"')
    start = html.find('<p align="center"><a href="https://github.com/wochenlong')
    if start < 0:
        start = html.find('<div class="sd-home')
    end = html.find("</div><!--[--><!--]--></div><footer class=\"page-meta\">")
    if start < 0 or end < 0:
        raise SystemExit("index.html body markers not found")
    INDEX_HTML.write_text(html[:start] + HOME_HUB_HTML + html[end:], encoding="utf-8")
    meta = INDEX_META.read_text(encoding="utf-8")
    meta = meta.replace('"title":"SD-Trainer"', '"title":"Next Trainer"')
    INDEX_META.write_text(meta, encoding="utf-8")
    print("patched index.html + meta")


def write_guide_assets() -> None:
    GUIDE_HTML.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "key": GUIDE_KEY,
        "path": "/help/guide.html",
        "title": "新手上路",
        "lang": "en-US",
        "frontmatter": {},
        "excerpt": "",
        "headers": [],
        "filePathRelative": "help/guide.md",
    }
    GUIDE_DATA_JS.write_text(
        f"const t=JSON.parse({json.dumps(json.dumps(data, ensure_ascii=False))});export{{t as data}};",
        encoding="utf-8",
    )
    inner = GUIDE_HTML_BODY.replace("\\", "\\\\").replace("`", "\\`")
    GUIDE_COMP_JS.write_text(
        'import{_ as n,o as s,c as a,e as i}from"./app.547295de.js";'
        f"const _={{}},h=i(`{inner}`);"
        "function u(){return s(),a(\"div\",null,[h])}"
        'var x=n(_,[["render",u],["__file","guide.html.vue"]]);export{x as default};',
        encoding="utf-8",
    )
    # SSR page from changelog template
    tpl = (DIST / "other/changelog.html").read_text(encoding="utf-8")
    g = tpl.replace("/other/changelog.md", "/help/guide.md")
    g = g.replace("更新日志", "新手上路", 2)
    g = g.replace("changelog.html", "guide.html")
    g = g.replace("changelog.html.a1b2c3d4", "guide.html.b8e2d701")
    g = g.replace("changelog.html.e5f6a7b8", "guide.html.c3f4a902")
    a = g.find("<h2 id=")
    b = g.find("</div><!--[--><!--]--></div><footer")
    g = g[:a] + GUIDE_HTML_BODY + g[b:]
    g = g.replace("<title>更新日志 | SD 训练 UI</title>", "<title>新手上路 | SD 训练 UI</title>")
    GUIDE_HTML.write_text(g, encoding="utf-8")
    print("wrote help/guide")


CHANGELOG_KEY = "v-a1c9e4f2"


def patch_app_routes() -> None:
    """Register guide/changelog chunks only — sidebar JSON via patch-sidebar-nav.py."""
    js = APP_JS.read_text(encoding="utf-8")
    if GUIDE_KEY not in js:
        anchor = '"v-b5471278":()=>wt(()=>import("./about.html.5b0c0de9.js"),[]).then(({data:e})=>e),'
        if anchor not in js:
            raise SystemExit("about data import anchor not found")
        js = js.replace(
            anchor,
            anchor
            + f'"{GUIDE_KEY}":()=>wt(()=>import("./guide.html.b8e2d701.js"),[]).then(({{data:e}})=>e),',
            1,
        )
        anchor2 = '"v-b5471278":Jt(()=>wt(()=>import("./about.html.b4807002.js"),[])),'
        js = js.replace(
            anchor2,
            anchor2 + f'"{GUIDE_KEY}":Jt(()=>wt(()=>import("./guide.html.c3f4a902.js"),[])),',
            1,
        )
    if CHANGELOG_KEY not in js:
        anchor = '"v-b5471278":()=>wt(()=>import("./about.html.5b0c0de9.js"),[]).then(({data:e})=>e),'
        js = js.replace(
            anchor,
            anchor
            + f'"{CHANGELOG_KEY}":()=>wt(()=>import("./changelog.html.a1b2c3d4.js"),[]).then(({{data:e}})=>e),',
            1,
        )
        anchor2 = '"v-b5471278":Jt(()=>wt(()=>import("./about.html.b4807002.js"),[])),'
        js = js.replace(
            anchor2,
            anchor2
            + f'"{CHANGELOG_KEY}":Jt(()=>wt(()=>import("./changelog.html.e5f6a7b8.js"),[])),',
            1,
        )
    route_anchor = '["v-b5471278","/other/about.html",{title:""},["/other/about","/other/about.md"]],'
    if route_anchor in js:
        extra = ""
        if CHANGELOG_KEY not in js[js.find(route_anchor) : js.find(route_anchor) + 400]:
            extra += (
                f'["{CHANGELOG_KEY}","/other/changelog.html",{{title:"\\u66F4\\u65B0\\u65E5\\u5FD7"}},'
                f'["/other/changelog","/other/changelog.md"]],'
            )
        if GUIDE_KEY not in js[js.find(route_anchor) : js.find(route_anchor) + 600]:
            extra += (
                f'["{GUIDE_KEY}","/help/guide.html",{{title:"\\u65b0\\u624b\\u4e0a\\u8def"}},'
                f'["/help/guide","/help/guide.md"]],'
            )
        if extra:
            js = js.replace(route_anchor, route_anchor + extra, 1)
    APP_JS.write_text(js, encoding="utf-8")
    print("patched app.js routes")


def patch_home_css() -> None:
    css_path = ASSETS / "sd-trainer-ui-polish.css"
    css = css_path.read_text(encoding="utf-8")
    old = re.search(
        r"/\* ----- 首页引导 ----- \*/.*?(?=/\* ----- 中栏)",
        css,
        re.DOTALL,
    )
    new_block = """
/* ----- 首页：Next Trainer 传送门 ----- */
main.page .theme-default-content > div[align="center"] h1 {
  font-size: 1.75rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  margin-bottom: 0.25rem;
}

main.page .theme-default-content > div[align="center"] > p {
  font-size: 0.9375rem;
  color: var(--c-text-lighter, #606266);
  margin-top: 0;
}

main.page .theme-default-content .sd-home-hub {
  max-width: 40rem;
  margin: 0.75rem auto 2rem;
  text-align: left;
}

main.page .theme-default-content .sd-home-badges {
  margin: 0.5rem 0 1.25rem;
}

main.page .theme-default-content .sd-home-lead {
  font-size: 0.9375rem;
  line-height: 1.65;
  color: var(--c-text, #404244);
  margin: 0 0 1.5rem;
}

main.page .theme-default-content .sd-home-section-title {
  font-size: 0.8125rem;
  font-weight: 650;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--c-text-lighter, #909399);
  margin: 0 0 0.65rem;
  padding: 0;
  border: none;
}

main.page .theme-default-content .sd-home-portals {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.65rem;
  margin-bottom: 1.35rem;
}

@media (max-width: 520px) {
  main.page .theme-default-content .sd-home-portals {
    grid-template-columns: 1fr;
  }
}

main.page .theme-default-content .sd-home-portals--single {
  grid-template-columns: 1fr;
  max-width: 20rem;
}

main.page .theme-default-content .sd-home-portal {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding: 0.85rem 1rem;
  border-radius: var(--sd-radius-md);
  border: 1px solid var(--c-border, #e4e7ed);
  background: var(--c-bg-mute, #fff);
  text-decoration: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.12s ease;
}

main.page .theme-default-content .sd-home-portal:hover {
  border-color: color-mix(in srgb, var(--el-color-primary) 35%, var(--c-border));
  box-shadow: var(--sd-shadow-sm);
  transform: translateY(-1px);
}

main.page .theme-default-content .sd-home-portal--primary {
  border-left: 3px solid var(--el-color-primary);
  background: color-mix(in srgb, var(--el-color-primary) 5%, #fff);
}

main.page .theme-default-content .sd-home-portal--monitor {
  border-color: color-mix(in srgb, var(--el-color-primary) 25%, var(--c-border));
  background: color-mix(in srgb, var(--el-color-primary) 4%, var(--c-bg-light, #f8f9fb));
}

main.page .theme-default-content .sd-home-portal__title {
  font-size: 1rem;
  font-weight: 650;
  color: var(--c-text, #303133);
}

main.page .theme-default-content .sd-home-portal__desc {
  font-size: 0.8125rem;
  color: var(--c-text-lighter, #909399);
  line-height: 1.4;
}

main.page .theme-default-content .sd-home-foot {
  font-size: 0.8125rem;
  line-height: 1.6;
  color: var(--c-text-lighter, #909399);
  text-align: center;
  margin: 0;
  padding-top: 0.5rem;
  border-top: 1px solid var(--c-border, #e4e7ed);
}

main.page .theme-default-content .sd-home-foot a {
  color: var(--el-color-primary);
  font-weight: 500;
}

/* 帮助 · 新手上路 */
main.page .theme-default-content .sd-guide {
  max-width: 42rem;
  margin: 0 auto;
  line-height: 1.65;
}

main.page .theme-default-content .sd-guide h2 {
  margin: 1.25rem 0 0.65rem;
  padding-bottom: 0.35rem;
  font-size: 1.125rem;
  border-bottom: 1px solid var(--c-border);
}

main.page .theme-default-content .sd-guide ol,
main.page .theme-default-content .sd-guide ul {
  padding-left: 1.35rem;
}

main.page .theme-default-content .sd-guide li {
  margin: 0.35rem 0;
}

"""
    if old:
        css = css[: old.start()] + new_block + css[old.end() :]
    else:
        css = css.replace("/* ----- 中栏", new_block + "\n/* ----- 中栏", 1)
    css_path.write_text(css, encoding="utf-8")
    style = ASSETS / "style.874872ce.css"
    t = style.read_text(encoding="utf-8")
    s = t.find("/* ========== SD-Trainer UI polish")
    style.write_text(t[:s] + css, encoding="utf-8")
    print("patched home hub css")


def main() -> None:
    patch_index_js()
    patch_index_ssr()
    write_guide_assets()
    subprocess.run([sys.executable, str(PATCH_NAV)], check=True, cwd=ROOT)
    patch_app_routes()
    patch_home_css()
    print("done")


if __name__ == "__main__":
    main()

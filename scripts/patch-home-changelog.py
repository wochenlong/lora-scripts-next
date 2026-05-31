#!/usr/bin/env python3
"""Rewrite home page onboarding + add changelog page under 其他."""
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
ABOUT_HTML = DIST / "other/about.html"
CHANGELOG_HTML = DIST / "other/changelog.html"
CHANGELOG_DATA_JS = ASSETS / "changelog.html.a1b2c3d4.js"
CHANGELOG_COMP_JS = ASSETS / "changelog.html.e5f6a7b8.js"
PATCH_NAV = ROOT / "scripts/patch-sidebar-nav.py"
PATCH_PORTALS = ROOT / "scripts/patch-home-portals.py"

CHANGELOG_KEY = "v-a1c9e4f2"
CHANGELOG_DATA_CHUNK = "changelog.html.a1b2c3d4.js"
CHANGELOG_COMP_CHUNK = "changelog.html.e5f6a7b8.js"

CHANGELOG_HTML_INNER = """<p align="center"><a href="https://github.com/wochenlong/lora-scripts-next" style="margin:2px;"><img alt="GitHub Repo stars" src="https://img.shields.io/github/stars/wochenlong/lora-scripts-next"></a><a href="https://github.com/wochenlong/lora-scripts-next" style="margin:2px;"><img alt="GitHub forks" src="https://img.shields.io/github/forks/wochenlong/lora-scripts-next"></a><a href="https://raw.githubusercontent.com/wochenlong/lora-scripts-next/master/LICENSE" style="margin:2px;"><img src="https://img.shields.io/github/license/wochenlong/lora-scripts-next" alt="license"></a><a href="https://github.com/wochenlong/lora-scripts-next/releases" style="margin:2px;"><img src="https://img.shields.io/github/v/release/wochenlong/lora-scripts-next?color=blueviolet&amp;include_prereleases" alt="release"></a></p><h3 id="版本记录" tabindex="-1"><a class="header-anchor" href="#版本记录" aria-hidden="true">#</a> 版本记录</h3><h4 id="v2-7-0" tabindex="-1"><a class="header-anchor" href="#v2-7-0" aria-hidden="true">#</a> v2.7.0</h4><ul><li><strong>Anima LoRA Fast 模式</strong>：侧栏「Anima LoRA → Fast 模式」，可选插件 <code>anima_lora</code>（页内安装、独立 venv）</li><li>训练监控同步 Fast Loss / 进度 / 预览；文档 <code>docs/anima-fast.md</code></li><li>同参对标约 <strong>2.5×</strong> 加速（4090；标准 ≈7.1 s/step vs Fast ≈2.8 s/step）</li><li>整合包<strong>不预装</strong>插件 venv，首次在 Fast 页安装</li></ul><h4 id="v2-6-0" tabindex="-1"><a class="header-anchor" href="#v2-6-0" aria-hidden="true">#</a> v2.6.0</h4><ul><li><strong>Anima 全量微调</strong>：侧栏「全量微调 → Anima Finetune」，路由 <code>anima-finetune</code> → <code>anima_train.py</code></li><li>训练监控正确显示 <strong>Anima Finetune</strong>（不再误标为 LoRA）</li><li>文档与示例：<code>docs/anima-backend.md</code>、<code>docs/examples/anima-full-finetune.toml</code></li><li>显存参考：4090 实测专用显存约 23–24 GB（与 LoRA 的 12GB 档不同）</li></ul><h4 id="v2-5-3" tabindex="-1"><a class="header-anchor" href="#v2-5-3" aria-hidden="true">#</a> v2.5.3</h4><ul><li>便携包依赖健康检查、侧栏版本号（<a href="https://github.com/wochenlong/lora-scripts-next/issues/54" target="_blank" rel="noopener noreferrer">#54</a>）</li></ul><h4 id="v2-5-0" tabindex="-1"><a class="header-anchor" href="#v2-5-0" aria-hidden="true">#</a> v2.5.0</h4><ul><li>UI 焕新：侧栏导航重构，训练 / 工具 / 帮助分区清晰</li><li>首页传送门：卡片式入口快速跳转训练、监控、新手上路</li><li>训练监控仪表盘：GPU 实时指标、总步数、训练参数速查</li><li>CSS 去重清理（~1660 行冗余代码）</li></ul><h4 id="v2-4-0" tabindex="-1"><a class="header-anchor" href="#v2-4-0" aria-hidden="true">#</a> v2.4.0</h4><ul><li>训练子进程环境隔离，NaN 过滤，采样保护，attn_mode 降级</li><li>路径规范化；整合包 tkinter 修复</li></ul><h4 id="v2-3-0" tabindex="-1"><a class="header-anchor" href="#v2-3-0" aria-hidden="true">#</a> v2.3.0</h4><ul><li>TensorBoard 同源 Loss 曲线；训练参数速查；日志同步到监控页</li><li>整合包：跳过 triton-windows；run_gui 启动日志；跨盘监控修复</li></ul><h4 id="v2-1-0" tabindex="-1"><a class="header-anchor" href="#v2-1-0" aria-hidden="true">#</a> v2.1.0</h4><ul><li>Flash Attention 2 预构建 Wheel（Windows 免编译）</li><li>按步数保存；LoKr 显示修复；跨盘监控修复</li></ul><h4 id="v2-0-0" tabindex="-1"><a class="header-anchor" href="#v2-0-0" aria-hidden="true">#</a> v2.0.0</h4><ul><li>Windows 便携包首发；Flash Attention 自动加速；AMD 提示；bf16 修复</li></ul><h4 id="v1-next" tabindex="-1"><a class="header-anchor" href="#v1-next" aria-hidden="true">#</a> 基于原版的改进</h4><ul><li>Anima 训练（LoRA / LoKr / T-LoRA）</li><li>交互式 Loss 曲线；实时训练监控（端口 6008）</li><li>Anima 后端迁移至 kohya-ss/sd-scripts</li></ul><h3 id="原版更新日志" tabindex="-1"><a class="header-anchor" href="#原版更新日志" aria-hidden="true">#</a> 原版更新日志</h3><p>本项目 Fork 自 <a href="https://github.com/Akegarasu/lora-scripts" target="_blank" rel="noopener noreferrer">Akegarasu/lora-scripts</a>，完整记录见仓库根目录 <a href="https://github.com/wochenlong/lora-scripts-next/blob/main/CHANGELOG.md" target="_blank" rel="noopener noreferrer">CHANGELOG.md</a>。</p>"""

HOME_BODY_HTML = """<div class="sd-home-onboarding"><h2 id="项目简介" tabindex="-1"><a class="header-anchor" href="#项目简介" aria-hidden="true">#</a> 项目简介</h2><p><strong>SD-Trainer</strong> 是基于秋叶版 <a href="https://github.com/Akegarasu/lora-scripts" target="_blank" rel="noopener noreferrer">lora-scripts</a> 的 Stable Diffusion 训练 WebUI（本 fork：<a href="https://github.com/wochenlong/lora-scripts-next" target="_blank" rel="noopener noreferrer">lora-scripts-next</a>）。在浏览器里配置模型路径、数据集与训练参数，一键启动训练；支持 LoRA、Dreambooth、Anima、Flux 等。</p><h2 id="新手上路" tabindex="-1"><a class="header-anchor" href="#新手上路" aria-hidden="true">#</a> 新手上路</h2><ol><li><strong>准备数据</strong>：图片 + 同名标签文件；可用左侧「工具与调试 → 数据集打标」。</li><li><strong>选训练类型</strong>：<ul><li>LoRA：<a href="/lora/sd3.html"><strong>Anima</strong></a>、<a href="/lora/anima-fast.html"><strong>Anima Fast</strong></a>（进阶插件加速）、<a href="/lora/flux.html"><strong>Flux</strong></a>、<a href="/lora/master.html"><strong>Stable Diffusion</strong></a></li><li>全量微调：<a href="/lora/anima-finetune.html"><strong>Anima Finetune</strong></a>（完整 DiT，约 24GB 显存）、<a href="/dreambooth/index.html"><strong>Stable Diffusion</strong></a>（Dreambooth / SDXL）</li></ul></li><li><strong>填参数并开训</strong>：中栏表单 + 右栏「开始训练」；进度可开 <a href="/tensorboard.html">Tensorboard</a> 或 <a href="/train-monitor">训练监控</a>。</li></ol><h2 id="从秋叶版迁移" tabindex="-1"><a class="header-anchor" href="#从秋叶版迁移" aria-hidden="true">#</a> 从秋叶版迁移</h2><p>若你习惯原 <strong>Akegarasu/lora-scripts</strong>（秋叶一键包），本版主要变化如下：</p><ul><li><strong>导航</strong>：按「训练 / 工具 / 帮助 / 其他」分组；LoRA 下聚合 Anima、Flux、SD；原「新手 / 专家」不再平铺于侧栏（SD1.5 精简页仍可访问 <a href="/lora/basic.html">/lora/basic.html</a>）。</li><li><strong>Anima</strong>：原 SD3 位置改为 Anima 训练（Qwen + T5 + DiT）；进阶用户可选用 <a href="/lora/anima-fast.html">Fast 插件</a> 加速 LoRA。</li><li><strong>监控</strong>：独立训练监控页、Loss 曲线、实时日志（<code>/train-log</code>）。</li><li><strong>其他</strong>：便携包优化、Flash Attention 自动加速、AMD 提示等（详见 <a href="/other/changelog.html">更新日志</a>）。</li></ul><p class="sd-home-tip">参数含义见「帮助 → 训练参数说明」；反馈与联系方式见「其他 → 关于」。</p></div>"""

BADGES = """<p align="center"><a href="https://github.com/wochenlong/lora-scripts-next" style="margin:2px;"><img alt="GitHub Repo stars" src="https://img.shields.io/github/stars/wochenlong/lora-scripts-next"></a><a href="https://github.com/wochenlong/lora-scripts-next" style="margin:2px;"><img alt="GitHub forks" src="https://img.shields.io/github/forks/wochenlong/lora-scripts-next"></a><a href="https://raw.githubusercontent.com/wochenlong/lora-scripts-next/master/LICENSE" style="margin:2px;"><img src="https://img.shields.io/github/license/wochenlong/lora-scripts-next" alt="license"></a><a href="https://github.com/wochenlong/lora-scripts-next/releases" style="margin:2px;"><img src="https://img.shields.io/github/v/release/wochenlong/lora-scripts-next?color=blueviolet&amp;include_prereleases" alt="release"></a></p>"""


def patch_index_js() -> None:
    text = INDEX_JS.read_text(encoding="utf-8")
    start = text.find("h=r(`")
    end = text.find("`,10);function F")
    if start < 0 or end < 0:
        raise SystemExit("index template not found")
    start += len("h=r(`")
    text = text[:start] + BADGES + HOME_BODY_HTML + text[end:]
    INDEX_JS.write_text(text, encoding="utf-8")
    print(f"patched {INDEX_JS.relative_to(ROOT)}")


def patch_index_ssr_html() -> None:
    path = DIST / "index.html"
    html = path.read_text(encoding="utf-8")
    start = html.find('<p align="center"><a href="https://github.com/wochenlong/lora-scripts-next"')
    end = html.find("</div><!--[--><!--]--></div><footer class=\"page-meta\">")
    if start < 0 or end < 0:
        raise SystemExit("index.html markers not found")
    path.write_text(html[:start] + BADGES + HOME_BODY_HTML + html[end:], encoding="utf-8")
    print(f"patched {path.relative_to(ROOT)}")


def write_changelog_assets() -> None:
    data = {
        "key": CHANGELOG_KEY,
        "path": "/other/changelog.html",
        "title": "更新日志",
        "lang": "en-US",
        "frontmatter": {},
        "excerpt": "",
        "headers": [],
        "filePathRelative": "other/changelog.md",
    }
    CHANGELOG_DATA_JS.write_text(
        f"const t=JSON.parse({json.dumps(json.dumps(data, ensure_ascii=False))});export{{t as data}};",
        encoding="utf-8",
    )
    inner_escaped = CHANGELOG_HTML_INNER.replace("\\", "\\\\").replace("`", "\\`")
    comp = (
        'import{_ as n,r as o,o as s,c,a as e,b as r,e as i}from"./app.547295de.js";'
        f"const _={{}},h=i(`{inner_escaped}`);"
        "function u(g,p){return s(),c(\"div\",null,["
        'e("h2",{id:"\\u66F4\\u65B0\\u65E5\\u5FD7",tabindex:"-1"},'
        '[e("a",{class:"header-anchor",href:"#\\u66F4\\u65B0\\u65E5\\u5FD7","aria-hidden":"true"},"#"),'
        'r(" \\u66F4\\u65B0\\u65E5\\u5FD7")],-1),h])}'
        'var x=n(_,[["render",u],["__file","changelog.html.vue"]]);export{x as default};'
    )
    CHANGELOG_COMP_JS.write_text(comp, encoding="utf-8")
    print("wrote changelog js chunks")


def create_changelog_html() -> None:
    src = ABOUT_HTML.read_text(encoding="utf-8")
    html = src.replace("/other/about.md", "/other/changelog.md", 1)
    html = html.replace('class="sidebar-item active" aria-label="关于"', 'class="sidebar-item" aria-label="关于"')
    html = html.replace(
        '<li><a href="/other/settings.md" class="sidebar-item" aria-label="UI 设置">',
        '<li><a href="/other/settings.md" class="sidebar-item" aria-label="UI 设置">',
    )
    if 'aria-label="更新日志"' not in html:
        html = html.replace(
            '<li><a href="/other/about.md" class="sidebar-item" aria-label="关于">',
            '<li><a href="/other/changelog.md" class="sidebar-item active" aria-label="更新日志">'
            "<!--[--><!--]--> 更新日志 <!--[--><!--]--></a><!----></li>"
            '<li><a href="/other/about.md" class="sidebar-item" aria-label="关于">',
        )
    html = html.replace("about.html.b4807002.js", CHANGELOG_COMP_CHUNK)
    html = html.replace("about.html.5b0c0de9.js", CHANGELOG_DATA_CHUNK)
    main = (
        '<h2 id="更新日志" tabindex="-1">'
        '<a class="header-anchor" href="#更新日志" aria-hidden="true">#</a> 更新日志</h2>'
        + CHANGELOG_HTML_INNER
    )
    m = re.search(
        r"<div class=\"theme-default-content\">.*?<div>",
        html,
        re.DOTALL,
    )
    if not m:
        raise SystemExit("theme-default-content not found in about template")
    # replace inner content in about - find h2 关于
    a = html.find('<h2 id="关于"')
    b = html.find("</div><!--[--><!--]--></div><footer")
    if a < 0:
        a = html.find("<div>", html.find("theme-default-content")) + 5
    html = html[:a] + main + html[b:]
    html = html.replace("<title>SD 训练 UI</title>", "<title>更新日志 | SD 训练 UI</title>")
    CHANGELOG_HTML.write_text(html, encoding="utf-8")
    print(f"wrote {CHANGELOG_HTML.relative_to(ROOT)}")


def patch_app_js_routes() -> None:
    js = APP_JS.read_text(encoding="utf-8")
    if CHANGELOG_KEY in js:
        print("changelog routes already present")
        return
    js = js.replace(
        '"v-b5471278":()=>wt(()=>import("./about.html.5b0c0de9.js"),[]).then(({data:e})=>e),',
        '"v-b5471278":()=>wt(()=>import("./about.html.5b0c0de9.js"),[]).then(({data:e})=>e),'
        f'"{CHANGELOG_KEY}":()=>wt(()=>import("./{CHANGELOG_DATA_CHUNK}"),[]).then(({{data:e}})=>e),',
        1,
    )
    js = js.replace(
        '"v-b5471278":Jt(()=>wt(()=>import("./about.html.b4807002.js"),[])),',
        '"v-b5471278":Jt(()=>wt(()=>import("./about.html.b4807002.js"),[])),'
        f'"{CHANGELOG_KEY}":Jt(()=>wt(()=>import("./{CHANGELOG_COMP_CHUNK}"),[])),',
        1,
    )
    route_entry = (
        f'["{CHANGELOG_KEY}","/other/changelog.html",{{title:"\\u66F4\\u65B0\\u65E5\\u5FD7"}},'
        f'["/other/changelog","/other/changelog.md"]],'
    )
    js = js.replace(
        '["v-b5471278","/other/about.html",{title:""},["/other/about","/other/about.md"]],',
        '["v-b5471278","/other/about.html",{title:""},["/other/about","/other/about.md"]],'
        + route_entry,
        1,
    )
    APP_JS.write_text(js, encoding="utf-8")
    print(f"patched routes in {APP_JS.relative_to(ROOT)}")


def add_home_css() -> None:
    css_path = ASSETS / "sd-trainer-ui-polish.css"
    css = css_path.read_text(encoding="utf-8")
    block = """
/* ----- 首页引导 ----- */
main.page .theme-default-content .sd-home-onboarding {
  text-align: left;
  max-width: 42rem;
  margin: 0 auto;
}

main.page .theme-default-content .sd-home-onboarding h2 {
  margin: 1.5rem 0 0.75rem;
  padding-bottom: 0.4rem;
  font-size: 1.125rem;
  font-weight: 650;
  border-bottom: 1px solid var(--c-border, #e4e7ed);
}

main.page .theme-default-content .sd-home-onboarding h2:first-of-type {
  margin-top: 0.5rem;
}

main.page .theme-default-content .sd-home-onboarding ol,
main.page .theme-default-content .sd-home-onboarding ul {
  padding-left: 1.35rem;
  line-height: 1.65;
  color: var(--c-text, #303133);
}

main.page .theme-default-content .sd-home-onboarding li {
  margin: 0.35rem 0;
}

main.page .theme-default-content .sd-home-onboarding a {
  color: var(--el-color-primary);
  font-weight: 500;
}

main.page .theme-default-content .sd-home-tip {
  margin-top: 1.25rem;
  padding: 0.65rem 0.85rem;
  font-size: 0.875rem;
  color: var(--c-text-lighter, #606266);
  background: var(--c-bg-light, #f3f4f5);
  border-radius: var(--sd-radius-md);
  border: 1px solid var(--c-border, #e4e7ed);
}
"""
    if "sd-home-onboarding" not in css:
        css = css.replace("/* ----- 中栏：秋叶白表单区", block + "\n/* ----- 中栏：秋叶白表单区", 1)
        css_path.write_text(css, encoding="utf-8")
        style = ASSETS / "style.874872ce.css"
        t = style.read_text(encoding="utf-8")
        s = t.find("/* ========== SD-Trainer UI polish")
        style.write_text(t[:s] + css, encoding="utf-8")
        print("added home onboarding css")


def main() -> None:
    write_changelog_assets()
    create_changelog_html()
    patch_app_js_routes()
    subprocess.run([sys.executable, str(PATCH_NAV)], check=True, cwd=ROOT)
    subprocess.run([sys.executable, str(PATCH_PORTALS)], check=True, cwd=ROOT)
    print("done")


if __name__ == "__main__":
    main()

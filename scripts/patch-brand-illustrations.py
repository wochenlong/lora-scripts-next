#!/usr/bin/env python3
"""Copy Next Trainer brand art into frontend/dist and patch home / guide / changelog pages."""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "doc" / "local" / "Next Trainer" / "Next Trainer"
DIST = ROOT / "frontend" / "dist"
ASSETS = DIST / "assets"
ASSET_VERSION = "20260525-nt5"

HOME_LOGO = f"/assets/home-logo.webp?v={ASSET_VERSION}"
GUIDE_MASCOT = f"/assets/guide-mascot.webp?v={ASSET_VERSION}"
CHANGELOG_BANNER = f"/assets/changelog-banner.webp?v={ASSET_VERSION}"

GUIDE_BODY = f"""<div class="sd-guide"><div class="sd-guide-intro"><div class="sd-guide-intro__art" aria-hidden="true"><img src="{GUIDE_MASCOT}" alt="" loading="lazy" decoding="async"></div><div class="sd-guide-intro__body"><h2 id="新手上路" tabindex="-1"><a class="header-anchor" href="#新手上路" aria-hidden="true">#</a> 新手上路</h2><ol><li><strong>准备数据</strong>：训练图片 + 同名 <code>.txt</code> 标签；可用「工具与调试 → 数据集打标」。</li><li><strong>选择训练类型</strong>（侧栏「训练」）：<ul><li><a href="/lora/sd3.html"><strong>Anima</strong></a> — Anima DiT（推荐）</li><li><a href="/lora/flux.html"><strong>Flux</strong></a></li><li><a href="/lora/master.html"><strong>Stable Diffusion</strong></a> — 默认 SDXL</li><li><a href="/dreambooth/index.html"><strong>Dreambooth 训练</strong></a></li></ul></li><li><strong>填写参数并开训</strong>：中栏表单 → 右栏「开始训练」。</li><li><strong>查看进度</strong>：<a href="/monitor/" target="_blank" rel="noopener noreferrer">训练监控</a>、<a href="/tensorboard/">Tensorboard</a>。</li></ol></div></div><section class="sd-guide-migrate"><h2 id="从秋叶版迁移" tabindex="-1"><a class="header-anchor" href="#从秋叶版迁移" aria-hidden="true">#</a> 从秋叶版迁移</h2><p>若你使用过 <strong>Akegarasu/lora-scripts</strong>（秋叶一键包），本版主要变化：</p><ul><li><strong>品牌</strong>：项目名 <strong>lora-scripts-next</strong> / Next Trainer，侧栏按「训练 / 工具 / 帮助 / 其他」分组。</li><li><strong>导航</strong>：LoRA 下为 Anima、Flux、Stable Diffusion；原「新手 / 专家」不再平铺（SD1.5 精简页：<a href="/lora/basic.html">/lora/basic.html</a>）。</li><li><strong>Anima</strong>：原 SD3 入口改为 Anima（Qwen + T5 + DiT）。</li><li><strong>监控</strong>：独立 <a href="/monitor/" target="_blank" rel="noopener noreferrer">训练监控页</a>、Loss 曲线、<code>/train-log</code> 日志流。</li><li>更多版本说明见 <a href="/other/changelog.html">更新日志</a>。</li></ul></section></div>"""

CHANGELOG_BANNER_HTML = (
    f'<div class="sd-changelog-banner"><img src="{CHANGELOG_BANNER}" '
    f'alt="Next Trainer" loading="lazy" width="960" height="420"></div>'
)

BRAND_CSS = """
/* ----- 品牌插图：首页 Logo / 新手上路 / 更新日志 ----- */
main.page .theme-default-content > div[align="center"] h1.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

main.page .theme-default-content > div[align="center"] .sd-home-logo {
  display: block;
  width: min(300px, 86vw);
  height: auto;
  margin: 0.75rem auto 0.5rem;
  border-radius: 18px;
  box-shadow: 0 10px 32px color-mix(in srgb, var(--el-color-primary) 16%, transparent);
}

main.page .theme-default-content .sd-guide {
  max-width: 56rem;
  margin: 0 auto;
  line-height: 1.65;
  padding: 1.5rem 1.75rem 1.4rem;
  border-radius: var(--sd-radius-md, 12px);
  border: 1px solid var(--c-border, #e4e7ed);
  background: linear-gradient(
    160deg,
    color-mix(in srgb, var(--el-color-primary) 5%, #fff) 0%,
    var(--c-bg-mute, #fff) 72%
  );
}

/* 上：大立绘 + 新手上路（同高配对） */
main.page .theme-default-content .sd-guide-intro {
  display: grid;
  grid-template-columns: minmax(13rem, 22rem) minmax(0, 1fr);
  gap: 1.5rem 2.75rem;
  align-items: center;
}

main.page .theme-default-content .sd-guide-intro__art {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

main.page .theme-default-content .sd-guide-intro__art img {
  display: block;
  width: auto;
  max-width: 21rem;
  height: auto;
  max-height: 28rem;
  object-fit: contain;
  object-position: center center;
  filter: drop-shadow(0 10px 24px color-mix(in srgb, var(--el-color-primary) 16%, transparent));
}

main.page .theme-default-content .sd-guide-intro__body {
  min-width: 0;
}

main.page .theme-default-content .sd-guide-intro__body h2,
main.page .theme-default-content .sd-guide-migrate h2 {
  margin: 0 0 0.75rem;
  padding-bottom: 0.4rem;
  font-size: 1.2rem;
  border-bottom: 1px solid var(--c-border);
}

/* 下：迁移说明通栏，不再左侧留白 */
main.page .theme-default-content .sd-guide-migrate {
  margin-top: 1.5rem;
  padding: 1.2rem 1.35rem 1.1rem;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--el-color-primary) 12%, var(--c-border));
  background: color-mix(in srgb, var(--el-color-primary) 3%, #fff);
}

main.page .theme-default-content .sd-guide-migrate h2 {
  margin-top: 0;
}

main.page .theme-default-content .sd-guide ol,
main.page .theme-default-content .sd-guide ul {
  padding-left: 1.35rem;
}

main.page .theme-default-content .sd-guide li {
  margin: 0.35rem 0;
}

/* 新手上路：柔和链接色，避免默认亮蓝抢眼 */
main.page .theme-default-content .sd-guide a:not(.header-anchor) {
  color: #555a63;
  text-decoration: underline;
  text-decoration-color: color-mix(in srgb, var(--c-text-lighter, #909399) 55%, transparent);
  text-underline-offset: 0.15em;
  text-decoration-thickness: 1px;
  font-weight: 500;
  transition: color 0.15s ease, text-decoration-color 0.15s ease;
}

main.page .theme-default-content .sd-guide a:not(.header-anchor):hover {
  color: color-mix(in srgb, #4a4f57 82%, var(--el-color-primary));
  text-decoration-color: color-mix(in srgb, var(--el-color-primary) 45%, #c0c4cc);
}

main.page .theme-default-content .sd-guide a:not(.header-anchor) strong {
  color: inherit;
  font-weight: 650;
}

main.page .theme-default-content .sd-guide h2 .header-anchor {
  color: var(--c-text-lighter, #c0c4cc);
  text-decoration: none;
  font-weight: 400;
}

@media (max-width: 820px) {
  main.page .theme-default-content .sd-guide-intro {
    grid-template-columns: 1fr;
    gap: 1rem;
  }

  main.page .theme-default-content .sd-guide-intro__art img {
    max-width: 13.5rem;
    max-height: 20rem;
    margin: 0 auto;
  }
}

main.page .theme-default-content .sd-changelog {
  max-width: 48rem;
  margin: 0 auto;
}

main.page .theme-default-content .sd-changelog-banner {
  margin: 0 0 1.25rem;
  border-radius: var(--sd-radius-md, 12px);
  overflow: hidden;
  border: 1px solid var(--c-border, #e4e7ed);
  box-shadow: var(--sd-shadow-sm, 0 4px 14px rgba(0, 0, 0, 0.06));
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--el-color-primary) 4%, #fff) 0%,
    var(--c-bg-mute, #fff) 100%
  );
  line-height: 0;
}

main.page .theme-default-content .sd-changelog-banner img {
  display: block;
  width: 100%;
  height: auto;
  object-fit: contain;
  object-position: center;
}

main.page .theme-default-content .sd-changelog .sd-home-badges,
main.page .theme-default-content .sd-changelog > p[align="center"] {
  margin-bottom: 1rem;
}
"""


def export_webp(src: Path, dest: Path, max_width: int | None = None) -> None:
    img = Image.open(src)
    if max_width and img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.Resampling.LANCZOS)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, format="WEBP", quality=88, method=6)


def copy_assets() -> None:
    export_webp(SRC / "icon_2.png", ASSETS / "home-logo.webp", max_width=640)
    export_webp(SRC / "mascot_trans.png", ASSETS / "guide-mascot.webp", max_width=680)
    export_webp(SRC / "banner.png", ASSETS / "changelog-banner.webp", max_width=1200)
    print("exported home-logo.webp, guide-mascot.webp, changelog-banner.webp")


def patch_home_logo() -> None:
    index_js = ASSETS / "index.html.c6ef684b.js"
    text = index_js.read_text(encoding="utf-8")
    text = text.replace(
        'var t="/assets/icon.65fd68ba.webp?v=20260525-nt"',
        f'var t="{HOME_LOGO}"',
    )
    text = text.replace(
        'C=s("img",{src:t,width:"200",height:"200",alt:"Next Trainer",style:{margin:"20px","border-radius":"25px"}},null,-1)',
        'C=s("img",{src:t,width:"300",height:"300",alt:"Next Trainer",class:"sd-home-logo",loading:"lazy"},null,-1)',
    )
    text = text.replace(
        'y=s("h1",{id:"next-trainer",tabindex:"-1"},[s("a",{class:"header-anchor",href:"#next-trainer","aria-hidden":"true"},"#"),n(" Next Trainer")],-1)',
        'y=s("h1",{id:"next-trainer",class:"sr-only",tabindex:"-1"},[s("a",{class:"header-anchor",href:"#next-trainer","aria-hidden":"true"},"#"),n(" Next Trainer")],-1)',
    )
    index_js.write_text(text, encoding="utf-8")

    index_html = DIST / "index.html"
    html = index_html.read_text(encoding="utf-8")
    html = re.sub(
        r'<img src="/assets/icon\.65fd68ba\.webp[^"]*" width="200" height="200" alt="Next Trainer"[^>]*>',
        f'<img src="{HOME_LOGO}" class="sd-home-logo" width="300" height="300" alt="Next Trainer" loading="lazy">',
        html,
        count=1,
    )
    html = html.replace(
        '<h1 id="next-trainer" tabindex="-1">',
        '<h1 id="next-trainer" class="sr-only" tabindex="-1">',
        1,
    )
    index_html.write_text(html, encoding="utf-8")
    print("patched home logo (icon_2)")


def patch_guide_page() -> None:
    guide_html = DIST / "help" / "guide.html"
    html = guide_html.read_text(encoding="utf-8")
    html = re.sub(
        r'<div class="sd-guide">.*?</div></div><!--\[--><!--\]--></div><footer',
        GUIDE_BODY + '</div><!--[--><!--]--></div><footer',
        html,
        count=1,
        flags=re.DOTALL,
    )
    html = re.sub(
        r'/assets/guide-mascot\.webp\?v=[^"]+',
        GUIDE_MASCOT,
        html,
    )
    guide_html.write_text(html, encoding="utf-8")

    guide_js = ASSETS / "guide.html.c3f4a902.js"
    inner = GUIDE_BODY.replace("\\", "\\\\").replace("`", "\\`")
    guide_js.write_text(
        'import{_ as n,o as s,c as a,e as i}from"./app.547295de.js";'
        f"const _={{}},h=i(`{inner}`);"
        "function u(){return s(),a(\"div\",null,[h])}"
        'var x=n(_,[["render",u],["__file","guide.html.vue"]]);export{x as default};',
        encoding="utf-8",
    )
    print("patched help/guide (mascot layout)")


def patch_changelog_page() -> None:
    changelog_html = DIST / "other" / "changelog.html"
    html = changelog_html.read_text(encoding="utf-8")
    if "sd-changelog-banner" not in html:
        html = html.replace(
            '<div><h2 id="更新日志"',
            f'<div class="sd-changelog">{CHANGELOG_BANNER_HTML}<h2 id="更新日志"',
            1,
        )
        html = html.replace(
            "</div><!--[--><!--]--></div><footer class=\"page-meta\">",
            "</div></div><!--[--><!--]--></div><footer class=\"page-meta\">",
            1,
        )
    html = re.sub(
        r'/assets/changelog-banner\.webp\?v=[^"]+',
        CHANGELOG_BANNER,
        html,
    )
    changelog_html.write_text(html, encoding="utf-8")

    changelog_js = ASSETS / "changelog.html.e5f6a7b8.js"
    text = changelog_js.read_text(encoding="utf-8")
    text = re.sub(
        r'/assets/changelog-banner\.webp\?v=[^"]+',
        CHANGELOG_BANNER,
        text,
    )
    if "sd-changelog-banner" not in text:
        banner_esc = CHANGELOG_BANNER_HTML.replace("\\", "\\\\").replace("`", "\\`")
        text = text.replace(
            'function u(g,p){return s(),c("div",null,[e("h2"',
            'function u(g,p){return s(),c("div",{class:"sd-changelog"},['
            f'i(`{banner_esc}`),e("h2"',
            1,
        )
        text = text.replace("],-1),h])}", "],-1),h])}", 1)
        changelog_js.write_text(text, encoding="utf-8")
    print("patched other/changelog (banner)")


def append_brand_css() -> None:
    css_path = ASSETS / "sd-trainer-ui-polish.css"
    css = css_path.read_text(encoding="utf-8")
    css = re.sub(
        r"/\* 帮助 · 新手上路 \*/.*?(?=/\* ----- 品牌插图|\* ----- 中栏)",
        "",
        css,
        count=1,
        flags=re.DOTALL,
    )
    marker = "/* ----- 品牌插图：首页 Logo / 新手上路 / 更新日志 ----- */"
    if marker in css:
        css = re.sub(
            re.escape(marker) + r".*?(?=/\* ----- 中栏|\Z)",
            BRAND_CSS.strip() + "\n\n",
            css,
            count=1,
            flags=re.DOTALL,
        )
    else:
        css = css.replace("/* ----- 中栏", BRAND_CSS + "\n/* ----- 中栏", 1)
    css_path.write_text(css, encoding="utf-8")

    style = ASSETS / "style.874872ce.css"
    text = style.read_text(encoding="utf-8")
    start = text.find("/* ========== SD-Trainer UI polish")
    style.write_text(text[:start] + css, encoding="utf-8")
    print("patched brand illustration css")


def main() -> None:
    copy_assets()
    patch_home_logo()
    patch_guide_page()
    patch_changelog_page()
    append_brand_css()


if __name__ == "__main__":
    main()

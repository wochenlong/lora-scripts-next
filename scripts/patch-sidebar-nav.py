#!/usr/bin/env python3
"""Patch VuePress sidebar in app.js and SSR HTML files."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "frontend/dist/assets/app.547295de.js"
DIST = ROOT / "frontend/dist"

OLD_SIDEBAR_JSON = (
    '[{"text":"SD-Trainer","link":"/"},'
    '{"text":"LoRA\\u8bad\\u7ec3","link":"/lora/index.md","collapsible":false,"children":'
    '[{"text":"\\u65b0\\u624b\\uff08SD1.5\\uff09","link":"/lora/basic.md"},'
    '{"text":"\\u4e13\\u5bb6","link":"/lora/master.md"},'
    '{"text":"Flux","link":"/lora/flux.md"},'
    '{"text":"Anima LoRA","link":"/lora/sd3.md"},'
    '{"text":"Anima 全量","link":"/lora/anima-finetune.md"},'
    '{"text":"\\u5de5\\u5177","link":"/lora/tools.md"},'
    '{"text":"\\u53c2\\u6570\\u8be6\\u89e3","link":"/lora/params.md"}]},'
    '{"text":"Dreambooth \\u8bad\\u7ec3","link":"/dreambooth/index.md"},'
    '{"text":"Tensorboard","link":"/tensorboard.md"},'
    '{"text":"Tagger \\u6807\\u7b7e\\u5668","link":"/tagger.md"},'
    '{"text":"\\u6807\\u7b7e\\u7f16\\u8f91\\u5668","link":"/tageditor.md"},'
    '{"text":"\\u5176\\u4ed6","collapsible":false,"children":'
    '[{"text":"UI \\u8bbe\\u7f6e","link":"/other/settings.md"},'
    '{"text":"\\u5173\\u4e8e","link":"/other/about.md"}]}]'
)

def get_old_sidebar_from_file() -> str:
    js = APP_JS.read_text(encoding="utf-8")
    idx = js.find('"sidebar":')
    if idx < 0:
        raise RuntimeError("sidebar key not found")
    start = js.find("[", idx)
    if start < 0:
        raise RuntimeError("sidebar array not found")
    depth = 0
    for i in range(start, len(js)):
        if js[i] == "[":
            depth += 1
        elif js[i] == "]":
            depth -= 1
            if depth == 0:
                return js[start : i + 1]
    raise RuntimeError("sidebar not found")


NEW_SIDEBAR_JSON = (
    '[{"text":"Next Trainer","link":"/"},'
    '{"text":"训练","children":['
    '{"text":"LoRA 训练","link":"/lora/index.md","collapsible":false,"children":['
    '{"text":"Anima LoRA","link":"/lora/sd3.md"},'
    '{"text":"Flux","link":"/lora/flux.md"},'
    '{"text":"Stable Diffusion","link":"/lora/master.md"}]},'
    '{"text":"\\u5168\\u91cf\\u5fae\\u8c03","link":"/lora/anima-finetune.md","collapsible":false,"children":['
    '{"text":"Anima Finetune","link":"/lora/anima-finetune.md"},'
    '{"text":"Stable Diffusion","link":"/dreambooth/index.md"}]}]},'
    '{"text":"工具与调试","children":['
    '{"text":"Tensorboard","link":"/tensorboard.md"},'
    '{"text":"数据集打标","link":"/tagger.md"},'
    '{"text":"标签编辑","link":"/tageditor.md"},'
    '{"text":"LoRA 脚本工具","link":"/lora/tools.md"}]},'
    '{"text":"帮助","children":['
    '{"text":"新手上路","link":"/help/guide.md"},'
    '{"text":"训练参数说明","link":"/lora/params.md"}]},'
    '{"text":"其他","collapsible":false,"children":['
    '{"text":"UI 设置","link":"/other/settings.md"},'
    '{"text":"关于","link":"/other/about.md"},'
    '{"text":"更新日志","link":"/other/changelog.md"}]}]'
)


def item(href: str, label: str, aria: str, active: bool = False) -> str:
    cls = "sidebar-item active" if active else "sidebar-item"
    return (
        f'<li><a href="{href}" class="{cls}" aria-label="{aria}">'
        f"<!--[--><!--]--> {label} <!--[--><!--]--></a><!----></li>"
    )


def item_heading(href: str, label: str, aria: str, active: bool = False, close_li: bool = True) -> str:
    cls = "sidebar-item sidebar-heading active" if active else "sidebar-item sidebar-heading"
    tail = "<!----></li>" if close_li else ""
    return (
        f'<li><a href="{href}" class="{cls}" aria-label="{aria}">'
        f"<!--[--><!--]--> {label} <!--[--><!--]--></a><!---->"
        f"{tail}"
    )


def group_heading(title: str, expanded: bool = True) -> str:
    style = '""' if expanded else '"display:none;"'
    return (
        f'<li><p tabindex="0" class="sidebar-item sidebar-heading">{title} <!----></p>'
        f'<ul style={style} class="sidebar-item-children">'
    )


def build_sidebar_html(rel_path: str) -> str:
    """rel_path like lora/sd3.html relative to frontend/dist."""
    web = "/" + rel_path.replace("\\", "/")
    if web.endswith("/index.html"):
        web_md = web.replace("/index.html", "/index.md")
    elif web.endswith(".html"):
        web_md = web.replace(".html", ".md")
    else:
        web_md = web

    def active(href: str) -> bool:
        return href == web_md or href.replace(".md", ".html") == web

    lora_heading_active = active("/lora/index.md")
    finetune_heading_active = active("/dreambooth/index.md") or active("/lora/anima-finetune.md")
    train_expanded = (
        lora_heading_active
        or finetune_heading_active
        or active("/lora/sd3.md")
        or active("/lora/flux.md")
        or active("/lora/master.md")
        or active("/lora/basic.md")
        or active("/lora/sdxl.md")
    )
    # LoRA 子项仅由 app.js 导航在客户端渲染；SSR 不要再写 <ul>，否则会重复一份
    lora_block = item_heading(
        "/lora/index.md", "LoRA训练", "LoRA训练", lora_heading_active, close_li=True
    )

    train_block = (
        group_heading("训练", train_expanded)
        + "<!--[-->"
        + lora_block
        + item_heading(
            "/lora/anima-finetune.md",
            "全量微调",
            "全量微调",
            finetune_heading_active,
        )
        + "<!--]--></ul></li>"
    )

    tools_expanded = (
        active("/tensorboard.md")
        or active("/tagger.md")
        or active("/tageditor.md")
        or active("/lora/tools.md")
    )
    tools_block = (
        group_heading("工具与调试", tools_expanded)
        + "<!--[-->"
        + item_heading(
            "/tensorboard.md", "Tensorboard", "Tensorboard", active("/tensorboard.md")
        )
        + item_heading("/tagger.md", "数据集打标", "数据集打标", active("/tagger.md"))
        + item_heading("/tageditor.md", "标签编辑", "标签编辑", active("/tageditor.md"))
        + item(
            "/lora/tools.md",
            "LoRA 脚本工具",
            "LoRA 脚本工具",
            active("/lora/tools.md"),
        )
        + "<!--]--></ul></li>"
    )

    help_expanded = active("/help/guide.md") or active("/lora/params.md")
    help_block = (
        group_heading("帮助", help_expanded)
        + "<!--[-->"
        + item("/help/guide.md", "新手上路", "新手上路", active("/help/guide.md"))
        + item(
            "/lora/params.md",
            "训练参数说明",
            "训练参数说明",
            active("/lora/params.md"),
        )
        + "<!--]--></ul></li>"
    )

    other_expanded = (
        active("/other/settings.md")
        or active("/other/about.md")
        or active("/other/changelog.md")
    )
    other_block = (
        group_heading("其他", other_expanded)
        + "<!--[-->"
        + item("/other/settings.md", "UI 设置", "UI 设置", active("/other/settings.md"))
        + item("/other/about.md", "关于", "关于", active("/other/about.md"))
        + item("/other/changelog.md", "更新日志", "更新日志", active("/other/changelog.md"))
        + "<!--]--></ul></li>"
    )

    return (
        '<li><a href="/" class="sidebar-item sidebar-heading" aria-label="Next Trainer">'
        "<!--[--><!--]--> Next Trainer <!--[--><!--]--></a><!----></li>"
        + train_block
        + tools_block
        + help_block
        + other_block
    )


SIDEBAR_ITEMS_RE = re.compile(
    r"(<ul class=\"sidebar-items\"[^>]*><!--\[-->)"
    r".*?"
    r"(<!--\]--></ul><ul class=\"sidebar-bottom\")",
    re.DOTALL,
)


def patch_app_js() -> None:
    js = APP_JS.read_text(encoding="utf-8")
    old = get_old_sidebar_from_file()
    if old not in js:
        raise SystemExit("old sidebar JSON mismatch")
    APP_JS.write_text(js.replace(old, NEW_SIDEBAR_JSON, 1), encoding="utf-8")
    print(f"patched {APP_JS}")


def patch_html(path: Path) -> None:
    html = path.read_text(encoding="utf-8")
    if "sidebar-items" not in html:
        return
    new_inner = build_sidebar_html(path.relative_to(DIST).as_posix())
    m = SIDEBAR_ITEMS_RE.search(html)
    if not m:
        print(f"WARN: sidebar pattern miss {path}")
        return
    html = SIDEBAR_ITEMS_RE.sub(rf"\1{new_inner}\2", html, count=1)
    path.write_text(html, encoding="utf-8")
    print(f"patched {path.relative_to(ROOT)}")


def main() -> None:
    patch_app_js()
    for html in sorted(DIST.rglob("*.html")):
        if html.name == "404.html":
            continue
        patch_html(html)


if __name__ == "__main__":
    main()

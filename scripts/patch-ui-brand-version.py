#!/usr/bin/env python3
"""Inject sd-trainer-brand.js (version chip) into built HTML pages."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend" / "dist"
STYLE = DIST / "assets" / "style.874872ce.css"
MARKER = "sd-trainer-brand.js"

VERSION_CHIP_CSS = """
/* 版本号：贴在「Next Trainer」标题右侧 */
.sd-brand-version-chip {
  position: fixed;
  top: 0;
  left: 0;
  z-index: 20;
  padding: 0.12rem 0.5rem;
  border-radius: var(--sd-radius-pill, 999px);
  font-size: 0.72rem;
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: 0.04em;
  font-variant-numeric: tabular-nums;
  color: var(--sd-nav-secondary-label, #909399);
  background: color-mix(in srgb, var(--c-bg, #fff) 92%, transparent);
  border: 1px solid var(--c-border, #e4e7ed);
  pointer-events: none;
  user-select: none;
  white-space: nowrap;
}
html.dark .sd-brand-version-chip {
  color: var(--c-text-lighter, #a3a6ad);
  background: color-mix(in srgb, var(--c-bg, #22272e) 92%, transparent);
  border-color: var(--c-border, #3d444d);
}
"""


def script_tag() -> str:
    ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip() or "0"
    return f'<script src="/assets/sd-trainer-brand.js?v={ver}" defer></script>'


def ensure_version_css() -> None:
    if not STYLE.is_file():
        print("skip css: style bundle missing")
        return
    style = STYLE.read_text(encoding="utf-8")
    if ".sd-brand-version-chip" in style:
        return
    STYLE.write_text(style.rstrip() + "\n" + VERSION_CHIP_CSS, encoding="utf-8")
    print("appended version chip css to style bundle")


def patch_html_files() -> None:
    ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip() or "0"
    tag = script_tag()
    count = 0
    for path in DIST.rglob("*.html"):
        html = path.read_text(encoding="utf-8")
        original = html
        if MARKER not in html:
            needle = '<script type="module" src="/assets/app.'
            if needle in html:
                html = html.replace(needle, tag + "\n    " + needle, 1)
        html = re.sub(
            r'src="/assets/sd-trainer-brand\.js(\?v=[^"]*)?"',
            f'src="/assets/sd-trainer-brand.js?v={ver}"',
            html,
        )
        if html != original:
            path.write_text(html, encoding="utf-8")
            count += 1
    print(f"patched {count} html file(s) (brand script v={ver})")


def main() -> None:
    ensure_version_css()
    patch_html_files()


if __name__ == "__main__":
    main()

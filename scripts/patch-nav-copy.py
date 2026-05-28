#!/usr/bin/env python3
"""Update page titles and intro copy after nav restructure."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend/dist"

REPLACEMENTS = [
    ("<strong>Anima LoRA</strong>", "<strong>Anima</strong>"),
    ('aria-label="Anima LoRA"', 'aria-label="Anima"'),
    ("LoRA 训练 专家模式 | SD 训练 UI", "Stable Diffusion LoRA | SD 训练 UI"),
    ('"title":"LoRA 训练 专家模式"', '"title":"Stable Diffusion LoRA"'),
    ("LoRA 训练 专家模式</h1>", "Stable Diffusion LoRA</h1>"),
    ("lora-训练-专家模式", "stable-diffusion-lora"),
    ("#lora-训练-专家模式", "#stable-diffusion-lora"),
    ("LoRA 相关工具 | SD 训练 UI", "LoRA 脚本工具 | SD 训练 UI"),
    ('"title":"LoRA 相关工具"', '"title":"LoRA 脚本工具"'),
    ("LoRA 相关工具</h1>", "LoRA 脚本工具</h1>"),
    ("LoRA 相关工具", "LoRA 脚本工具"),
    (
        "<p>本 LoRA 训练界面分为两种模式。</p><ul><li>针对新手的简易训练只有部分可调节参数</li><li>针对有一定经验的用户的专家模式，开放全部的高级参数</li></ul><div class=\"custom-container tip\"><p class=\"custom-container-title\">TIP</p><p>如果你是新手，建议使用新手模式，不要逞强使用专家模式，否则可能会出现意想不到的问题。</p></div>",
        "<p>LoRA 为<strong>局部微调</strong>；全量微调请使用侧栏 <strong>全量微调</strong>（Stable Diffusion 或 Anima Finetune）。</p>"
        "<ul>"
        "<li><strong>Anima</strong> — 主推训练入口（Anima DiT）</li>"
        "<li><strong>Flux</strong> — Flux 模型 LoRA</li>"
        "<li><strong>Stable Diffusion</strong> — SD1.5 / SDXL（页顶切换训练种类，默认 SDXL）</li>"
        "</ul>"
        "<p>打标、看日志、脚本工具等在侧栏 <strong>工具与调试</strong>；参数说明在 <strong>帮助</strong>。</p>"
        "<p>SD1.5 精简参数页仍保留：<a href=\"/lora/basic.html\">/lora/basic.html</a></p>",
    ),
    (
        "<p>你所热爱的 就是你的参数</p>",
        "<p>SD1.5 与 SDXL 共用本页：在「训练种类」中切换。默认 SDXL。SD1.5 精简入口见 <a href=\"/lora/basic.html\">SD1.5 精简</a>。</p>",
    ),
]

OLD_INDEX_SNIP = "本 LoRA 训练界面分为两种模式"


def patch_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    orig = text
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    if text != orig:
        path.write_text(text, encoding="utf-8")
        print(f"updated {path.relative_to(ROOT)}")


def main() -> None:
    for path in DIST.rglob("*"):
        if path.suffix not in {".html", ".js"}:
            continue
        if "404" in path.name:
            continue
        if OLD_INDEX_SNIP in path.read_text(encoding="utf-8") or any(
            old in path.read_text(encoding="utf-8") for old, _ in REPLACEMENTS[:6]
        ):
            patch_file(path)


if __name__ == "__main__":
    main()

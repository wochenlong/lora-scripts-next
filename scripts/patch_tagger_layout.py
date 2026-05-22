"""Inject tagger progress zone into vendored layout bundle."""
from pathlib import Path

LAYOUT = Path("frontend/dist/assets/layout.96d49288.js")
MARKER = 'onClick:a},{default:withCtx(()=>[createTextVNode("\\u542F\\u52A8")]),_:1})'
ZONE = (
    'createBaseVNode("div",{id:"tagger-run-zone",class:"tagger-run-zone"},'
    '[createBaseVNode("div",{class:"tagger-run-zone__bar",role:"progressbar","aria-valuemin":"0","aria-valuemax":"100"},'
    '[createBaseVNode("div",{class:"tagger-run-zone__bar-fill"})]),'
    'createBaseVNode("p",{class:"tagger-run-zone__text"})]),'
)


def main() -> None:
    text = LAYOUT.read_text(encoding="utf-8")
    if "tagger-run-zone" in text:
        print("already patched")
        return
    idx = text.find(MARKER)
    if idx < 0:
        raise SystemExit("tagger start button marker not found")
    # insert zone + comma before createVNode(d,...启动 button
    start = text.rfind("createVNode(d,{style:{margin:\"10px 20px 0 20px\"}", 0, idx)
    if start < 0:
        raise SystemExit("createVNode anchor not found")
    text = text[:start] + ZONE + text[start:]
    LAYOUT.write_text(text, encoding="utf-8")
    print("patched", LAYOUT)


if __name__ == "__main__":
    main()

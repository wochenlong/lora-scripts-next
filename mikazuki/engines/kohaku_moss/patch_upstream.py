"""Apply the pinned Windows compiler-failure fallback to KohakuMossTrainer."""
from __future__ import annotations

import sys
from pathlib import Path


IMPORT_MARKER = "import subprocess"
ERROR_MARKER = "    subprocess.CalledProcessError,"


def apply_patch(source: Path) -> bool:
    target = source / "src" / "kohakumoss_kernels" / "errors.py"
    text = target.read_text(encoding="utf-8")
    if IMPORT_MARKER in text and ERROR_MARKER in text:
        return False
    if "import torch\n" not in text or "    UnicodeError,\n" not in text:
        raise RuntimeError(f"unexpected pinned upstream content: {target}")
    text = text.replace("import torch\n", "import subprocess\n\nimport torch\n", 1)
    text = text.replace(
        "    UnicodeError,\n",
        "    UnicodeError,\n    subprocess.CalledProcessError,\n",
        1,
    )
    target.write_text(text, encoding="utf-8")
    return True


def main() -> int:
    source = Path(sys.argv[1]).resolve()
    changed = apply_patch(source)
    print("Applied Windows build fallback patch." if changed else "Windows build fallback patch already applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

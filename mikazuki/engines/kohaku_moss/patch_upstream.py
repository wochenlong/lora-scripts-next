"""Apply the pinned Windows compiler-failure fallback to KohakuMossTrainer."""
from __future__ import annotations

import sys
from pathlib import Path

IMPORT_MARKER = "import subprocess"
ERROR_MARKER = "    subprocess.CalledProcessError,"
LYCORIS_PROBE_MARKER = "status.probe(name, device)"

LYCORIS_OLD = """    if requested != "auto" and requested not in available_backends(device):
        raise ValueError(
            f"KERNELS['lycoris']={requested!r} is not available on {device}; "
            f"available: {available_backends(device)}"
        )
    return resolve_backend(None if requested == "auto" else requested, device)"""

LYCORIS_NEW = """    from lycoris.kernels.dispatch import FUSED, demote
    from kohakumoss_kernels import status
    from kohakumoss_kernels.registry import load_backends
    load_backends()
    for name in (*FUSED, "compile"):
        if name in available_backends(device) and status.probe(name, device) is not None:
            demote(name, device)
    if requested != "auto" and requested not in available_backends(device):
        raise ValueError(
            f"KERNELS['lycoris']={requested!r} is not available on {device}; "
            f"available: {available_backends(device)}"
        )
    return resolve_backend(None if requested == "auto" else requested, device)"""


def apply_patch(source: Path) -> bool:
    changed = False
    target = source / "src" / "kohakumoss_kernels" / "errors.py"
    text = target.read_text(encoding="utf-8")
    if not (IMPORT_MARKER in text and ERROR_MARKER in text):
        if "import torch\n" not in text or "    UnicodeError,\n" not in text:
            raise RuntimeError(f"unexpected pinned upstream content: {target}")
        text = text.replace("import torch\n", "import subprocess\n\nimport torch\n", 1)
        text = text.replace(
            "    UnicodeError,\n",
            "    UnicodeError,\n    subprocess.CalledProcessError,\n",
            1,
        )
        target.write_text(text, encoding="utf-8")
        changed = True

    lycoris_target = source / "src" / "kohakumoss" / "adapters" / "lycoris" / "backend.py"
    if lycoris_target.is_file():
        lyco_text = lycoris_target.read_text(encoding="utf-8")
        if LYCORIS_PROBE_MARKER not in lyco_text:
            if LYCORIS_OLD not in lyco_text:
                raise RuntimeError(f"unexpected pinned upstream content: {lycoris_target}")
            lyco_text = lyco_text.replace(LYCORIS_OLD, LYCORIS_NEW, 1)
            lycoris_target.write_text(lyco_text, encoding="utf-8")
            changed = True
    return changed


def main() -> int:
    source = Path(sys.argv[1]).resolve()
    changed = apply_patch(source)
    print("Applied Windows build fallback patch." if changed else "Windows build fallback patch already applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

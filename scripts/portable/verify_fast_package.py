"""Offline checks for the explicitly marked GUI + Fast portable profile."""

import argparse
import importlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys


def require_inside(path, root):
    if not Path(path).resolve().is_relative_to(root.resolve()):
        raise RuntimeError(f"Runtime escapes package: {path}")


def verify(root, cuda=False, audit=False, gui_only=False):
    if gui_only and (cuda or audit):
        raise ValueError("GUI-only checks cannot replace a CUDA or engine audit")
    root = Path(root).resolve()
    profile = json.loads((root / "portable-profile.json").read_text(encoding="utf-8"))
    if profile != {"version": 1, "profile": "gui-fast"}:
        raise RuntimeError("Unknown portable profile")
    for path in (sys.executable, sys.prefix, sys.base_prefix):
        require_inside(path, root)
    # These are host imports, deliberately not training-engine dependencies.
    for name in ("toml", "fastapi", "uvicorn", "multipart", "psutil",
                 "tensorboard", "PIL", "numpy", "requests", "rich",
                 "huggingface_hub", "modelscope", "cryptography"):
        module = importlib.import_module(name)
        if getattr(module, "__file__", None):
            require_inside(module.__file__, root)
    if gui_only:
        print("Standalone GUI checks passed; engine readiness is managed in the GUI.")
        return
    app = root / "Next-Trainer"
    extension = app / "extensions/anima_lora"
    repair = runpy.run_path(str(app / "mikazuki/engines/anima_fast/portable_runtime.py"))
    repair["repair"](extension)
    env = os.environ.copy()
    env.update(PYTHONNOUSERSITE="1", PYTHONPATH="", PYTHONHOME="")
    probe = """
import json, sys, torch, accelerate, safetensors
from pathlib import Path
root = Path(sys.argv[1]).resolve()
paths = [sys.executable, sys.prefix, sys.base_prefix, torch.__file__,
         accelerate.__file__, safetensors.__file__, *sys.path]
for path in paths:
    if not Path(path).resolve().is_relative_to(root):
        raise RuntimeError("Runtime escapes package: " + path)
if sys.argv[2] == "cuda":
    assert torch.cuda.is_available(), "CUDA unavailable"
    assert (torch.ones(8, device="cuda") * 2).sum().item() == 16
print(json.dumps({"paths": paths, "torch": torch.__version__,
                  "cuda_checked": sys.argv[2] == "cuda"}))
"""
    result = subprocess.run(
        [str(extension / ".venv/Scripts/python.exe"), "-I", "-c", probe,
         str(root), "cuda" if cuda else "imports"],
        cwd=app, env=env, check=True, capture_output=True, text=True)
    print(result.stdout.strip())
    if audit:
        sys.path.insert(0, str(app))
        from mikazuki.engines.anima_fast.environment import audit_environment
        from mikazuki.engines.anima_fast.extension_state import (
            ExtensionLayout, STATE_READY, STATE_BROKEN, write_install_state,
        )
        layout = ExtensionLayout(extension)
        result = audit_environment(app, layout, require_cuda=cuda)
        write_install_state(layout, STATE_READY if result.ok else STATE_BROKEN,
                            {"audit": result.as_dict()}, "portable build audit")
        if not result.ok:
            raise RuntimeError("Fast engine audit failed: " + "; ".join(result.errors))
    print("Standalone GUI + Fast runtime checks passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portable-root", type=Path, required=True)
    parser.add_argument("--cuda", action="store_true")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--gui-only", action="store_true")
    args = parser.parse_args()
    verify(args.portable_root, args.cuda, args.audit, args.gui_only)

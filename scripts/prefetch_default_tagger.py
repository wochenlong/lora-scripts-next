#!/usr/bin/env python3
"""Download the default WD tagger into HF cache and the visible tagger-models folder."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mikazuki.tagger.defaults import (  # noqa: E402
    DEFAULT_TAGGER_FILES,
    DEFAULT_TAGGER_KEY,
    DEFAULT_TAGGER_REPO_ID,
    DEFAULT_TAGGER_REVISION,
)
from mikazuki.tagger.local_models import (  # noqa: E402
    DEFAULT_TAGGER_MODELS_DIR,
    local_model_family,
)


def _resolve_hf_home(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get("HF_HOME")
    if env:
        return Path(env).resolve()
    return (REPO_ROOT / "huggingface").resolve()


def _resolve_tagger_models_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    return (REPO_ROOT / DEFAULT_TAGGER_MODELS_DIR).resolve()


def _default_local_model_dir(tagger_models_dir: Path) -> Path:
    return tagger_models_dir / local_model_family(DEFAULT_TAGGER_KEY) / DEFAULT_TAGGER_KEY


def is_default_tagger_in_local_dir(tagger_models_dir: Path | None = None) -> bool:
    model_dir = _default_local_model_dir(
        _resolve_tagger_models_dir(str(tagger_models_dir) if tagger_models_dir else None)
    )
    return all((model_dir / filename).is_file() for filename in DEFAULT_TAGGER_FILES)


def is_default_tagger_cached(hf_home: Path | None = None) -> bool:
    hf_home = _resolve_hf_home(str(hf_home) if hf_home else None)
    os.environ["HF_HOME"] = str(hf_home)
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        return False

    for filename in DEFAULT_TAGGER_FILES:
        try:
            hf_hub_download(
                repo_id=DEFAULT_TAGGER_REPO_ID,
                filename=filename,
                revision=DEFAULT_TAGGER_REVISION,
                local_files_only=True,
            )
        except Exception:
            return False
    return True


def ensure_default_tagger_model(
    hf_home: Path | None = None,
    *,
    tagger_models_dir: Path | None = None,
    use_china_mirror: bool = True,
    force: bool = False,
) -> Path:
    hf_home = _resolve_hf_home(str(hf_home) if hf_home else None)
    tagger_models_dir = _resolve_tagger_models_dir(
        str(tagger_models_dir) if tagger_models_dir else None
    )
    hf_home.mkdir(parents=True, exist_ok=True)
    model_dir = _default_local_model_dir(tagger_models_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(hf_home)
    os.environ["MIKAZUKI_TAGGER_MODELS_DIR"] = str(tagger_models_dir)

    if use_china_mirror and not os.environ.get("HF_ENDPOINT"):
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

    local_ready = is_default_tagger_in_local_dir(tagger_models_dir)
    if not force and local_ready:
        print(f"[tagger] Default model already present ({DEFAULT_TAGGER_KEY})")
        print(f"         local: {model_dir}")
        return model_dir

    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise SystemExit(
            "huggingface_hub is not installed. Run install-cn.ps1 / pip install -r requirements.txt first."
        ) from exc

    print(f"[tagger] Downloading default WD tagger: {DEFAULT_TAGGER_REPO_ID}")
    print(f"         revision={DEFAULT_TAGGER_REVISION} (~388 MB, please wait)")
    print(f"         HF_HOME={hf_home}")
    print(f"         local={model_dir}")
    if os.environ.get("HF_ENDPOINT"):
        print(f"         HF_ENDPOINT={os.environ['HF_ENDPOINT']}")

    for filename in DEFAULT_TAGGER_FILES:
        print(f"[tagger]   - {filename}")
        path = hf_hub_download(
            repo_id=DEFAULT_TAGGER_REPO_ID,
            filename=filename,
            revision=DEFAULT_TAGGER_REVISION,
        )
        print(f"[tagger]     -> {path}")
        target = model_dir / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        if force or not target.is_file():
            target.write_bytes(Path(path).read_bytes())
            print(f"[tagger]     local copy -> {target}")

    print(f"[tagger] Done. WebUI tagging can use '{DEFAULT_TAGGER_KEY}' offline.")
    return model_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hf-home",
        help="HF cache root (default: ./huggingface or HF_HOME env)",
    )
    parser.add_argument(
        "--tagger-models-dir",
        help=f"Visible tagger model root (default: ./{DEFAULT_TAGGER_MODELS_DIR})",
    )
    parser.add_argument(
        "--if-missing",
        action="store_true",
        help="Exit 0 without downloading when the model is already cached",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if cached",
    )
    parser.add_argument(
        "--no-mirror",
        action="store_true",
        help="Do not set HF_ENDPOINT to hf-mirror.com",
    )
    args = parser.parse_args()

    hf_home = _resolve_hf_home(args.hf_home)
    tagger_models_dir = _resolve_tagger_models_dir(args.tagger_models_dir)

    if args.if_missing and is_default_tagger_in_local_dir(tagger_models_dir) and not args.force:
        return 0

    ensure_default_tagger_model(
        hf_home,
        tagger_models_dir=tagger_models_dir,
        use_china_mirror=not args.no_mirror,
        force=args.force,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

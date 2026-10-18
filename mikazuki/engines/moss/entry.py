"""Thin pinned-source coordinator. --check-only parses real requests, no GPU work."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from mikazuki.engines.moss.adapter import AdaptedConfig, argv_for
from mikazuki.engines.moss.inputs import check_output, validate_cache, write_cache_identity
from mikazuki.engines.moss.extension_state import source_commit
from mikazuki.engines.moss.manifest import UPSTREAM
from mikazuki.engines.moss.preflight import check_inputs
from mikazuki.engines.moss.resource import environment_lock
from mikazuki.engines.moss.settings import Runtime
from mikazuki.engines.moss.source_integrity import verify_source


def validate_requests(adapted):
    # Source directory must already be on sys.path. This is the actual pinned
    # upstream parser, not a copied CLI or a mock training implementation.
    from library.moss.requests import CacheRequest, TrainRequest
    cache = CacheRequest.from_argv(argv_for(adapted.cache)) if adapted.run_preprocess else None
    train = TrainRequest.from_argv(argv_for(adapted.train))
    return cache, train


def execute_pipeline(runtime, adapted, runner=None):
    runner = runner or subprocess.run
    check_output(adapted.train["output"])
    cache_request, train_request = validate_requests(adapted)
    if cache_request is not None:
        print("[moss] preprocessing text and latents", flush=True)
        # Invalidate the empty-prompt cache when changing the encoder/cache
        # identity. Never delete user data: choose a fresh directory instead.
        empty = Path(adapted.train["cache"]) / "_empty.moss_te.safetensors"
        if adapted.cache["overwrite"] and empty.exists():
            raise ValueError("Use a fresh cache directory to replace an existing empty-prompt cache / 已有空提示缓存，请换新目录")
        runner([str(runtime.python), "-E", "-s", "-u", "-X", "utf8", "-m", "scripts.moss.cache", *cache_request.to_argv()], cwd=runtime.source, check=True)
        write_cache_identity(adapted)
    validate_cache(adapted, completed=True)
    check_output(adapted.train["output"])
    print("[moss] training LoRA", flush=True)
    runner([str(runtime.python), "-E", "-s", "-u", "-X", "utf8", "-m", "scripts.moss.train", *train_request.to_argv()], cwd=runtime.source, check=True)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--check-only", action="store_true", help="Parse actual upstream requests, never cache or train.")
    args = parser.parse_args(argv)
    runtime = Runtime(Path(args.project_root).resolve())
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    adapted = AdaptedConfig(**config)
    with environment_lock(runtime.root):
        if source_commit(runtime) != UPSTREAM["commit"]:
            raise ValueError("MOSS source pin changed; repair the engine / 源码版本不匹配，请修复引擎")
        verify_source(runtime)
        sys.path.insert(0, str(runtime.source))
        cache, train = validate_requests(adapted)
        if args.check_only:
            print(json.dumps({"source_commit": UPSTREAM["commit"], "cache": vars(cache) if cache else None,
                              "train": vars(train), "training_started": False}, ensure_ascii=False))
            return
        check_inputs(adapted)
        execute_pipeline(runtime, adapted)


if __name__ == "__main__":
    main()

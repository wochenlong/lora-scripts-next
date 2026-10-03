#!/usr/bin/env python3
"""Prefetch SDXL tokenizer vocab files into tokenizer-cache for offline training."""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mikazuki.networking.http import open_url
from mikazuki.china_hub import HF_TO_MODELSCOPE_REPOS  # noqa: E402
from mikazuki.tokenizer_cache import (  # noqa: E402
    BUNDLED_TOKENIZER_DIRS,
    DEFAULT_TOKENIZER_CACHE_DIRNAME,
    OPTIONAL_TOKENIZER_FILES_BY_REPO,
    TOKENIZER_FILES_BY_REPO,
    is_tokenizer_bundle_complete,
    required_tokenizer_files,
    tokenizer_local_dir,
)

MODELSCOPE_TOKENIZER_REPOS = HF_TO_MODELSCOPE_REPOS
HF_OFFICIAL_ENDPOINT = "https://huggingface.co"


def _resolve_cache_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    return (REPO_ROOT / DEFAULT_TOKENIZER_CACHE_DIRNAME).resolve()


def _download_via_modelscope(modelscope_repo: str, filename: str, dest: Path) -> None:
    from modelscope.hub.file_download import model_file_download

    downloaded = Path(model_file_download(modelscope_repo, filename))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(downloaded.read_bytes())


def _download_via_http(repo_id: str, filename: str, dest: Path, *, endpoint: str) -> None:
    url = f"{endpoint.rstrip('/')}/{repo_id}/resolve/main/{filename}"

    def _fetch(current_url: str, redirects: int = 0) -> bytes:
        if redirects > 8:
            raise RuntimeError(f"too many redirects for {current_url}")
        req = urllib.request.Request(current_url, headers={"User-Agent": "sd-trainer-prefetch"})
        try:
            with open_url(req, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308} and exc.headers.get("Location"):
                return _fetch(exc.headers["Location"], redirects + 1)
            raise

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(_fetch(url))


def _download_tokenizer_file(
    hf_repo_id: str,
    filename: str,
    dest: Path,
    *,
    prefer_modelscope: bool,
    hf_endpoint: str,
) -> None:
    errors: list[str] = []
    modelscope_repo = MODELSCOPE_TOKENIZER_REPOS.get(hf_repo_id, hf_repo_id)

    if prefer_modelscope:
        try:
            _download_via_modelscope(modelscope_repo, filename, dest)
            return
        except Exception as exc:
            errors.append(f"modelscope: {exc}")

    http_endpoints = [hf_endpoint]
    if hf_endpoint.rstrip("/") != HF_OFFICIAL_ENDPOINT:
        http_endpoints.append(HF_OFFICIAL_ENDPOINT)
    for endpoint in http_endpoints:
        try:
            _download_via_http(hf_repo_id, filename, dest, endpoint=endpoint)
            return
        except Exception as exc:
            errors.append(f"http({endpoint}): {exc}")

    if not prefer_modelscope:
        try:
            _download_via_modelscope(modelscope_repo, filename, dest)
            return
        except Exception as exc:
            errors.append(f"modelscope: {exc}")

    raise RuntimeError(f"failed to download {hf_repo_id}/{filename}: {'; '.join(errors)}")


def _optional_tokenizer_files(hf_repo_id: str) -> tuple[str, ...]:
    return OPTIONAL_TOKENIZER_FILES_BY_REPO.get(hf_repo_id, ())


def ensure_sdxl_tokenizer_cache(
    cache_root: Path,
    *,
    prefer_modelscope: bool = True,
    hf_endpoint: str = "https://hf-mirror.com",
    force: bool = False,
    include_flux_t5: bool = True,
) -> Path:
    cache_root.mkdir(parents=True, exist_ok=True)
    repo_ids = list(BUNDLED_TOKENIZER_DIRS.keys())
    if not include_flux_t5:
        repo_ids = [rid for rid in repo_ids if rid != "google/t5-v1_1-xxl"]
    if not force and is_tokenizer_bundle_complete(cache_root, repo_ids):
        print(f"Tokenizer cache already complete: {cache_root}")
        return cache_root

    for hf_repo_id in repo_ids:
        local_dir = tokenizer_local_dir(cache_root, hf_repo_id)
        for filename in required_tokenizer_files(hf_repo_id):
            dest = local_dir / filename
            if not force and dest.is_file():
                continue
            print(f"Downloading {hf_repo_id}/{filename} -> {dest}")
            _download_tokenizer_file(
                hf_repo_id,
                filename,
                dest,
                prefer_modelscope=prefer_modelscope,
                hf_endpoint=hf_endpoint,
            )
        for filename in _optional_tokenizer_files(hf_repo_id):
            dest = local_dir / filename
            if not force and dest.is_file():
                continue
            print(f"Downloading optional {hf_repo_id}/{filename} -> {dest}")
            try:
                _download_tokenizer_file(
                    hf_repo_id,
                    filename,
                    dest,
                    prefer_modelscope=prefer_modelscope,
                    hf_endpoint=hf_endpoint,
                )
            except Exception as exc:
                print(f"WARNING: optional tokenizer file skipped: {hf_repo_id}/{filename}: {exc}", file=sys.stderr)

    if not is_tokenizer_bundle_complete(cache_root, repo_ids):
        raise RuntimeError(f"tokenizer cache incomplete after prefetch: {cache_root}")
    print(f"Tokenizer cache ready: {cache_root}")
    return cache_root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        default="",
        help=f"Output directory (default: ./{DEFAULT_TOKENIZER_CACHE_DIRNAME})",
    )
    parser.add_argument("--if-missing", action="store_true", help="Skip when cache is already complete")
    parser.add_argument("--force", action="store_true", help="Re-download even when files exist")
    parser.add_argument(
        "--prefer-modelscope",
        action="store_true",
        default=True,
        help="Try ModelScope first (recommended for China build machines)",
    )
    parser.add_argument(
        "--no-prefer-modelscope",
        action="store_false",
        dest="prefer_modelscope",
        help="Try HTTP mirror first instead of ModelScope",
    )
    parser.add_argument(
        "--sdxl-only",
        action="store_true",
        help="Skip Flux T5-XXL tokenizer (~800 KB) and only prefetch SD/SDXL CLIP tokenizers",
    )
    parser.add_argument(
        "--hf-endpoint",
        default=os.environ.get("HF_ENDPOINT", "https://hf-mirror.com"),
        help="HF-style mirror base URL for HTTP fallback",
    )
    args = parser.parse_args()

    cache_root = _resolve_cache_root(args.cache_dir or None)
    repo_ids = list(BUNDLED_TOKENIZER_DIRS.keys())
    if args.sdxl_only:
        repo_ids = [rid for rid in repo_ids if rid != "google/t5-v1_1-xxl"]
    if args.if_missing and not args.force and is_tokenizer_bundle_complete(cache_root, repo_ids):
        print(f"Tokenizer cache already complete: {cache_root}")
        return 0

    ensure_sdxl_tokenizer_cache(
        cache_root,
        prefer_modelscope=args.prefer_modelscope,
        hf_endpoint=args.hf_endpoint,
        force=args.force,
        include_flux_t5=not args.sdxl_only,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import argparse
import os
import sys

from mikazuki.tagger.interrogator import available_interrogators
from mikazuki.tagger.service import (
    DEFAULT_API_PROMPT,
    DEFAULT_LOCAL_CAPTION_MODEL,
    DEFAULT_OPENAI_ENDPOINT,
    LocalBlipCaptionClient,
    OpenAICompatibleCaptionClient,
    run_api_tagger,
    run_caption_tagger,
    run_local_tagger,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mikazuki.tagger.cli",
        description="Batch tag/caption dataset images and write sidecar .txt files.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    local = subparsers.add_parser("local", help="Run a local WD/CL tagger and write TAG captions.")
    local.add_argument("--path", required=True, help="Image file, folder, or glob pattern.")
    local.add_argument(
        "--model",
        default="wd14-convnextv2-v2",
        choices=sorted(available_interrogators),
        help="Local tagger model key.",
    )
    local.add_argument("--threshold", type=float, default=0.35, help="General tag threshold.")
    local.add_argument("--character-threshold", type=float, default=0.6, help="Character tag threshold.")
    local.add_argument("--recursive", action="store_true", help="Search folders recursively.")
    local.add_argument("--additional-tags", default="", help="Comma-separated tags to append.")
    local.add_argument("--exclude-tags", default="", help="Comma-separated tags to remove.")
    local.add_argument("--use-cn-mirror", action="store_true", help="Use https://hf-mirror.com for missing model downloads.")
    local.add_argument("--hf-endpoint", help="Custom Hugging Face endpoint for missing model downloads.")
    local.add_argument(
        "--on-conflict",
        choices=("ignore", "copy", "prepend"),
        default="ignore",
        help="What to do when the sidecar .txt already exists.",
    )
    local.add_argument(
        "--replace-underscore",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Replace underscores with spaces in local tags.",
    )
    local.add_argument(
        "--escape-tag",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Escape parentheses and backslashes in local tags.",
    )

    api = subparsers.add_parser(
        "api",
        help="Call an OpenAI-compatible Chat Completions vision endpoint and write NL captions.",
    )
    api.add_argument("--path", required=True, help="Image file, folder, or glob pattern.")
    api.add_argument("--endpoint", default=DEFAULT_OPENAI_ENDPOINT, help="Base endpoint, e.g. https://api.openai.com/v1")
    api.add_argument("--model", required=True, help="Vision-capable chat model name.")
    api.add_argument("--prompt", default=DEFAULT_API_PROMPT, help="Prompt sent together with each image.")
    api.add_argument("--api-key", help="API key value. Takes precedence over --api-key-env.")
    api.add_argument("--api-key-env", default="OPENAI_API_KEY", help="Environment variable containing the API key.")
    api.add_argument("--timeout", type=float, default=60, help="Request timeout in seconds.")
    api.add_argument("--retries", type=int, default=2, help="Retry count per image.")
    api.add_argument("--recursive", action="store_true", help="Search folders recursively.")
    api.add_argument("--additional-tags", default="", help="Comma/newline fragment to append to API captions.")
    api.add_argument("--exclude-tags", default="", help="Comma/newline fragment to remove from API captions.")
    api.add_argument(
        "--on-conflict",
        choices=("ignore", "copy", "prepend"),
        default="ignore",
        help="What to do when the sidecar .txt already exists.",
    )

    caption = subparsers.add_parser(
        "caption",
        help="Run a local BLIP caption model and write NL captions.",
    )
    caption.add_argument("--path", required=True, help="Image file, folder, or glob pattern.")
    caption.add_argument(
        "--model",
        default=DEFAULT_LOCAL_CAPTION_MODEL,
        help="Hugging Face BLIP-compatible caption model.",
    )
    caption.add_argument("--prompt", default="", help="Optional conditional caption prompt.")
    caption.add_argument("--device", default="auto", help="auto, cpu, cuda, or another torch device string.")
    caption.add_argument("--max-new-tokens", type=int, default=64, help="Maximum generated caption tokens.")
    caption.add_argument("--use-cn-mirror", action="store_true", help="Use https://hf-mirror.com for missing model downloads.")
    caption.add_argument("--hf-endpoint", help="Custom Hugging Face endpoint for missing model downloads.")
    caption.add_argument("--recursive", action="store_true", help="Search folders recursively.")
    caption.add_argument("--additional-tags", default="", help="Comma/newline fragment to append to captions.")
    caption.add_argument("--exclude-tags", default="", help="Comma/newline fragment to remove from captions.")
    caption.add_argument(
        "--on-conflict",
        choices=("ignore", "copy", "prepend"),
        default="ignore",
        help="What to do when the sidecar .txt already exists.",
    )
    return parser


def resolve_api_key(explicit_key: str | None, env_name: str) -> str | None:
    return explicit_key or os.environ.get(env_name)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "local":
            result = run_local_tagger(
                args.path,
                model=args.model,
                threshold=args.threshold,
                character_threshold=args.character_threshold,
                recursive=args.recursive,
                additional_tags=args.additional_tags,
                exclude_tags=args.exclude_tags,
                on_conflict=args.on_conflict,
                replace_underscore=args.replace_underscore,
                escape_tag=args.escape_tag,
                use_cn_mirror=args.use_cn_mirror,
                hf_endpoint=args.hf_endpoint,
            )
        elif args.command == "api":
            api_key = resolve_api_key(args.api_key, args.api_key_env)
            if not api_key:
                parser.error(f"API key is required: pass --api-key or set {args.api_key_env}")
            client = OpenAICompatibleCaptionClient(
                endpoint=args.endpoint,
                api_key=api_key,
                model=args.model,
                prompt=args.prompt,
                timeout=args.timeout,
                retries=args.retries,
            )
            result = run_api_tagger(
                args.path,
                client=client,
                recursive=args.recursive,
                additional_tags=args.additional_tags,
                exclude_tags=args.exclude_tags,
                on_conflict=args.on_conflict,
            )
        else:
            client = LocalBlipCaptionClient(
                model=args.model,
                prompt=args.prompt,
                device=args.device,
                max_new_tokens=args.max_new_tokens,
                use_cn_mirror=args.use_cn_mirror,
                hf_endpoint=args.hf_endpoint,
            )
            result = run_caption_tagger(
                args.path,
                client=client,
                recursive=args.recursive,
                additional_tags=args.additional_tags,
                exclude_tags=args.exclude_tags,
                on_conflict=args.on_conflict,
            )
    except Exception as error:
        print(f"tagger failed: {error}", file=sys.stderr)
        return 1

    print(
        "done: "
        f"found={result.found}, processed={result.processed}, "
        f"skipped={result.skipped}, failed={result.failed}"
    )
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

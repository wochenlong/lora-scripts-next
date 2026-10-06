"""Explicit, non-downloading acceptance of the managed visual lifecycle.

Usage: python tools/verify_managed_caption_runtime.py --root <fresh-root>
  --assets <locked-GGUF-directory> --runtime <llama-server> --samples <3 images>
Existing assets are linked only for intermediate development verification.
This script does not claim or replace Phase 4's fresh download/rebuild.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psutil

from mikazuki.llm.config import UnifiedConfigStore
from mikazuki.llm.local_vision import FILES, LocalVisionService
from mikazuki.llm.service import UnifiedLLMService
from mikazuki.tag_translation.translation_config import OnlineServiceConfig
from mikazuki.tagger.caption import CAPTION_SCHEMA, parse_caption_response


async def verify(args):
    root = Path(args.root)
    if root.exists():
        raise RuntimeError("verification root must be new")
    root.mkdir(parents=True)
    path = root / "translation.json"
    legacy = OnlineServiceConfig(path)
    legacy.save({"local": {"runtime_path": str(Path(args.runtime).resolve())}})
    store = UnifiedConfigStore(path)
    manager = LocalVisionService(root, legacy, store)
    for name, _size, _sha in FILES:
        os.link(Path(args.assets) / name, manager.root / name)
    service = UnifiedLLMService(store)
    report = {"kind": "intermediate-managed-runtime", "reuses_probe_assets": True,
              "phase_4": False, "samples": [], "peak_rss_bytes": 0}
    sampler = None

    async def sample_memory():
        while True:
            process = psutil.Process(manager._process.pid)
            report["peak_rss_bytes"] = max(report["peak_rss_bytes"], process.memory_info().rss)
            await asyncio.sleep(0.1)

    try:
        started = time.perf_counter()
        await manager.start_runtime()
        report["startup_seconds"] = round(time.perf_counter() - started, 3)
        report["running"] = manager.status()["state"] == "running"
        sampler = asyncio.create_task(sample_memory())
        for index, image in enumerate(args.samples):
            started = time.perf_counter()
            profile, envelope, content, image_info = await service.complete_vision(
                image, '请用简体中文描述图片主要可见内容，只返回严格 JSON：{"caption":"中文描述","language":"zh-CN"}。',
                language="zh-CN", response_schema=CAPTION_SCHEMA, allow_local_fallback=True,
            )
            parsed = parse_caption_response(content, language="zh-CN")
            report["samples"].append({"index": index, "schema_valid": True,
                                      "caption_length": len(parsed.caption), "language": parsed.language,
                                      "seconds": round(time.perf_counter() - started, 3),
                                      "source": profile.source, "image": image_info,
                                      "finish_reason": envelope["choices"][0].get("finish_reason")})
        started = time.perf_counter()
        pending = asyncio.create_task(service.complete_vision(
            args.samples[0], "请用简体中文尽可能长地描述每个可见细节，输出不少于一千字的描述。",
            language="zh-CN", max_tokens=8192, allow_local_fallback=True,
        ))
        await asyncio.sleep(0.2)
        if pending.done():
            raise RuntimeError("cancellation request finished before cancellation")
        pending.cancel()
        try:
            await pending
        except asyncio.CancelledError:
            report["request_cancelled"] = True
        report["cancel_seconds"] = round(time.perf_counter() - started, 3)
        diagnostic = await service.connection_test(capability="vision", profile_id=profile.id, image_path=args.samples[0])
        report["healthy_after_cancel"] = diagnostic["ok"]
    finally:
        if sampler:
            sampler.cancel()
            await asyncio.gather(sampler, return_exceptions=True)
        await manager.stop_runtime()
        report["stopped"] = manager.status()["state"] != "running"
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if not all(report.get(key) for key in ["running", "request_cancelled", "healthy_after_cancel", "stopped"]):
        raise RuntimeError("managed visual acceptance failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--assets", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--samples", nargs=3, required=True)
    asyncio.run(verify(parser.parse_args()))

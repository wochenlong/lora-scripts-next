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
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psutil

from mikazuki.llm.config import UnifiedConfigStore
from mikazuki.llm.local_vision import ASSET_ID, FILES, LocalVisionService
from mikazuki.llm.service import UnifiedLLMService
from mikazuki.tag_translation.translation_config import OnlineServiceConfig
from mikazuki.tagger.caption import CAPTION_SCHEMA, parse_caption_response
from mikazuki.tagger.caption_job import CaptionJobManager, caption_sha256
from mikazuki.tagger.caption_store import CaptionJobStore
from mikazuki.llm.cache import CaptionCache


async def verify_batch(root, service, samples):
    images = root / "images"
    images.mkdir()
    for sample in samples:
        shutil.copy2(sample, images / Path(sample).name)
    cache = CaptionCache(root / "translations.sqlite3")
    journal = CaptionJobStore(cache.path)
    job = CaptionJobManager(service, cache=cache, job_store=journal)
    started = time.perf_counter()
    job.start({"path": str(images), "mode": "natural", "allow_local_fallback": True, "use_cache": False})
    await asyncio.to_thread(job._thread.join, 90)
    if job._thread.is_alive() or job.status()["succeeded"] != 3:
        job.cancel()
        await asyncio.to_thread(job._thread.join, 10)
        raise RuntimeError("real natural batch failed")
    report = {"batch_seconds": round(time.perf_counter() - started, 3), "batch_written": job.status()["succeeded"], "samples": []}
    for index, item in enumerate(job.status()["report"]["items"]):
        target = images / Path(item["filename"]).with_suffix(".txt")
        text = target.read_text(encoding="utf-8").strip()
        parse_caption_response(json.dumps({"caption": text, "language": "zh-CN"}), language="zh-CN")
        assert item["after_hash"] == caption_sha256(target)
        assert journal.find_format(target, item["after_hash"]) == "natural"
        report["samples"].append({"index": index, "schema_valid": True, "caption_length": len(text), "language": "zh-CN",
                                  "image_sha256": item["image_sha256"], "after_hash": item["after_hash"]})
    first = sorted(images.glob("*.png"))[0]
    target = first.with_suffix(".txt")

    class EditingService:
        async def complete_vision(self, *args, **kwargs):
            target.write_text("user edit preserved", encoding="utf-8")
            return await service.complete_vision(*args, **kwargs)

    conflict = CaptionJobManager(EditingService(), job_store=journal)
    conflict.start({"path": str(images), "paths": [str(first)], "mode": "natural", "allow_local_fallback": True, "use_cache": False})
    await asyncio.to_thread(conflict._thread.join, 45)
    assert not conflict._thread.is_alive()
    assert conflict.status()["errors"][0]["code"] == "caption_conflict"
    assert target.read_text() == "user edit preserved"
    report["real_conflict_preserved"] = True
    cancelled = CaptionJobManager(service, cache=cache, job_store=journal)
    before = target.read_bytes()
    cancelled.start({"path": str(images), "paths": [str(first)], "mode": "natural", "allow_local_fallback": True, "use_cache": False})
    await asyncio.sleep(.25)
    started = time.perf_counter()
    cancelled.cancel()
    await asyncio.to_thread(cancelled._thread.join, 5)
    assert not cancelled._thread.is_alive()
    assert cancelled.status()["phase"] == "cancelled"
    assert target.read_bytes() == before
    report["request_cancelled"] = True
    report["cancel_seconds"] = round(time.perf_counter() - started, 3)
    report["job_history_count"] = len(journal.history())
    return report


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
        if args.batch:
            report.update(await verify_batch(root, service, args.samples))
        for index, image in enumerate([] if args.batch else args.samples):
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
        if not args.batch:
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
        diagnostic = await service.connection_test(capability="vision", profile_id=ASSET_ID, image_path=args.samples[0])
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
    parser.add_argument("--batch", action="store_true", help="verify real natural writes, conflict and job cancellation")
    asyncio.run(verify(parser.parse_args()))

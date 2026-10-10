"""Explicit, non-downloading acceptance of the managed visual lifecycle.

Usage: python tools/verify_managed_caption_runtime.py --root <fresh-root>
  --assets <locked-GGUF-directory> --runtime <llama-server> --samples <3 images>
Existing assets are linked only for intermediate development verification.
This script does not claim or replace Phase 4's fresh download/rebuild.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import time
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psutil

from mikazuki.llm.config import UnifiedConfigStore
from mikazuki.llm.local_vision import ASSET_ID, FILES, LocalVisionService
from mikazuki.llm import model_manifest as locked
from mikazuki.llm.service import UnifiedLLMService
from mikazuki.llm.client import parse_json_content
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
        parse_caption_response(json.dumps({"caption": text, "language": "en"}), language="en")
        assert item["after_hash"] == caption_sha256(target)
        assert journal.find_format(target, item["after_hash"]) == "natural"
        report["samples"].append({"index": index, "schema_valid": True, "caption_length": len(text), "language": "en",
                                  "image_sha256": item["image_sha256"], "after_hash": item["after_hash"]})
    first = sorted(images.glob("*.png"))[0]
    target = first.with_suffix(".txt")

    class EditingService:
        async def complete_vision(self, *args, **kwargs):
            target.write_text("user edit preserved", encoding="utf-8")
            return await service.complete_vision(*args, **kwargs)

    conflict = CaptionJobManager(EditingService(), job_store=journal)
    conflict.start({"path": str(images), "paths": [str(first)], "mode": "natural", "allow_local_fallback": True, "use_cache": False, "conflict_action": "copy"})
    await asyncio.to_thread(conflict._thread.join, 45)
    assert not conflict._thread.is_alive()
    assert conflict.status()["errors"][0]["code"] == "caption_conflict"
    assert target.read_text() == "user edit preserved"
    report["real_conflict_preserved"] = True
    cancelled = CaptionJobManager(service, cache=cache, job_store=journal)
    before = target.read_bytes()
    cancelled.start({"path": str(images), "paths": [str(first)], "mode": "natural", "allow_local_fallback": True, "use_cache": False, "conflict_action": "copy"})
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
    # The managed service deliberately ignores legacy local.runtime_path. Put
    # the pinned archive in its managed install location and let the same
    # inventory/receipt extraction path used by production validate it.
    legacy.save({})
    store = UnifiedConfigStore(path)
    manager = LocalVisionService(root, legacy, store)
    for name, _size, _sha in FILES:
        source = Path(args.assets) / name
        if args.fresh_inputs:
            shutil.copy2(source, manager.root / name)
        else:
            os.link(source, manager.root / name)
    runtime_executable = Path(args.runtime).resolve()
    if not runtime_executable.is_file() or hashlib.sha256(runtime_executable.read_bytes()).hexdigest() != locked.EXECUTABLE_SHA256:
        raise RuntimeError("runtime executable does not match the locked receipt")
    runtime_archive = Path(args.runtime_archive).resolve()
    if not runtime_archive.is_file() or runtime_archive.stat().st_size != locked.RUNTIME_SIZE or hashlib.sha256(runtime_archive.read_bytes()).hexdigest() != locked.RUNTIME_SHA256:
        raise RuntimeError("runtime archive does not match the locked receipt")
    manager.archive_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(runtime_archive, manager.archive_path)
    await asyncio.to_thread(manager._extract_runtime)
    service = UnifiedLLMService(store)
    report = {"kind": "fresh-managed-runtime" if args.fresh_inputs else "intermediate-managed-runtime",
              "reuses_probe_assets": not args.fresh_inputs,
              "fresh_rebuild_inputs": bool(args.fresh_inputs), "phase_4": False, "samples": [], "peak_rss_bytes": 0,
              "asset_id": locked.ASSET_ID, "revision": locked.REVISION,
              "model_sha256": FILES[0][2], "mmproj_sha256": FILES[1][2],
              "runtime_version": locked.RUNTIME_VERSION,
              "runtime_sha256": locked.RUNTIME_SHA256,
              "source_commit": os.environ.get("MIKAZUKI_SOURCE_COMMIT", "working-tree")}
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
        translation_schema = {"type": "object", "additionalProperties": False,
                              "required": ["translation", "language"],
                              "properties": {"translation": {"type": "string", "minLength": 1, "maxLength": 300},
                                             "language": {"type": "string", "enum": ["zh-CN"]}}}
        _profile, envelope, content = await service.complete_text(
            'Translate "A red circle is on the left of a blue square." into Simplified Chinese. '
            'Return exactly JSON with translation and language; language must be "zh-CN".',
            language="zh-CN", response_schema=translation_schema, max_tokens=128,
            allow_local_fallback=True,
        )
        translated = parse_json_content(content)
        if (envelope.get("choices", [{}])[0].get("finish_reason") == "length"
                or set(translated) != {"translation", "language"}
                or translated.get("language") != "zh-CN"
                or not re.search(r"[\u3400-\u9fff]", str(translated.get("translation", "")))):
            raise RuntimeError("real local translation contract failed")
        report["translation"] = {"schema_valid": True, "language": "zh-CN",
                                  "source": _profile.source,
                                  "finish_reason": envelope["choices"][0].get("finish_reason")}
        sampler = asyncio.create_task(sample_memory())
        if args.batch:
            report.update(await verify_batch(root, service, args.samples))
        for index, image in enumerate([] if args.batch else args.samples):
            started = time.perf_counter()
            profile, envelope, content, image_info = await service.complete_vision(
                image, 'Describe the visible contents in English for an image training dataset. '
                       'Return only strict JSON: {"caption":"English description","language":"en"}.',
                language="en", response_schema=CAPTION_SCHEMA, allow_local_fallback=True,
            )
            parsed = parse_caption_response(content, language="en")
            report["samples"].append({"index": index, "schema_valid": True,
                                      "caption_length": len(parsed.caption), "language": parsed.language,
                                      "seconds": round(time.perf_counter() - started, 3),
                                      "source": profile.source, "image": image_info,
                                      "finish_reason": envelope["choices"][0].get("finish_reason")})
        if not args.batch:
            started = time.perf_counter()
            pending = asyncio.create_task(service.complete_vision(
            args.samples[0], "Describe every visible detail in English in a long response.",
            language="en", max_tokens=8192, allow_local_fallback=True,
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
    parser.add_argument("--runtime-archive", required=True)
    parser.add_argument("--samples", nargs=3, required=True)
    parser.add_argument("--batch", action="store_true", help="verify real natural writes, conflict and job cancellation")
    parser.add_argument("--fresh-inputs", action="store_true", help="assets come from a newly downloaded isolated rebuild root")
    asyncio.run(verify(parser.parse_args()))

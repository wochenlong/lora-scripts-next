"""Bounded real acceptance using production service/job/cache/write paths.

Remote credentials use a protected terminal and remain in the backend process.
Output includes processed caption files for review, never provider envelopes.
This intermediate verifier may reuse probe assets; it is not Phase 4.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sys
import getpass
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class BudgetSessions:
    def __init__(self, limit):
        self.limit = limit
        self.calls = 0
        self.image_requests = 0
        self.lock = threading.Lock()

    def __call__(self, **kwargs):
        import aiohttp
        kwargs["timeout"] = aiohttp.ClientTimeout(total=90)
        return self.Session(self, aiohttp.ClientSession(**kwargs))

    class Session:
        def __init__(self, budget, inner):
            self.budget, self.inner = budget, inner
        async def __aenter__(self):
            await self.inner.__aenter__()
            return self
        async def __aexit__(self, *args):
            return await self.inner.__aexit__(*args)
        def post(self, endpoint, **kwargs):
            with self.budget.lock:
                if self.budget.calls >= self.budget.limit:
                    raise RuntimeError("real verification request budget exhausted")
                self.budget.calls += 1
            payload = kwargs.get("json", {})
            for message in payload.get("messages", []):
                content = message["content"]
                if isinstance(content, list):
                    for part in content:
                        if part["type"] == "image_url":
                            url = part["image_url"]["url"]
                            assert url.startswith("data:image/jpeg;base64,")
                            assert len(url) <= 2 * 1024 * 1024 * 4 // 3 + 100
                            self.budget.image_requests += 1
                        elif part["type"] == "text":
                            assert not any(name in part["text"] for name in ["chelsea.png", "coffee.png", "rocket.jpg"])
            return self.inner.post(endpoint, **kwargs)


def run_job(manager, request):
    manager.start(request)
    manager._thread.join(300)
    if manager._thread.is_alive():
        manager.cancel()
        manager._thread.join(10)
        raise RuntimeError("production job exceeded time budget")
    status = manager.status()
    if status["succeeded"] != status["total"] or status["failed"]:
        codes = [item.get("code", "caption_failed") for item in status["errors"]]
        raise RuntimeError("production batch failed: " + ",".join(codes))
    return status


async def verify(args, key):
    if args.rebuild_inputs:
        from download_caption_rebuild_inputs import validate_inputs
        fresh, executable = validate_inputs(args.rebuild_inputs)
        if args.samples.resolve() != fresh / "samples" or args.assets.resolve() != fresh / "vision" or args.runtime.resolve() != executable:
            raise ValueError("rebuild acceptance must use its fresh downloaded inputs")
    root = args.root.resolve()
    if root.exists():
        raise RuntimeError("verification root must be new")
    os.environ["MIKAZUKI_TAG_TRANSLATION_ROOT"] = str(root)
    os.environ["MIKAZUKI_USER_DATA_ROOT"] = str(root / "user_data")
    if args.tag_models:
        os.environ["MIKAZUKI_TAGGER_MODELS_DIR"] = str(args.tag_models.resolve())
    from mikazuki.llm.config import UnifiedConfigStore
    from mikazuki.llm.service import UnifiedLLMService
    from mikazuki.llm.cache import CaptionCache
    from mikazuki.tagger.caption_store import CaptionJobStore
    from mikazuki.tagger.caption_job import CaptionJobManager, caption_sha256
    from mikazuki.tagger.task_bridge import CaptionTaskBridge
    from mikazuki.tagger.caption import CAPTION_SCHEMA, parse_caption_response, DEFAULT_CAPTION_PROMPT, render_prompt
    from mikazuki.llm.caption_translation import CaptionTextTranslator
    from mikazuki.tag_translation.translation_config import OnlineServiceConfig
    root.mkdir(parents=True, exist_ok=True)
    images = root / "images"
    images.mkdir()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    expected_sample_count = len(manifest.get("samples", []))
    if expected_sample_count < 1:
        raise ValueError("acceptance manifest must contain at least one sample")
    for item in manifest["samples"]:
        source = args.samples / item["filename"]
        assert hashlib.sha256(source.read_bytes()).hexdigest() == item["sha256"]
        shutil.copy2(source, images / item["filename"])
    config_path = root / "translation.json"
    legacy = OnlineServiceConfig(config_path)
    legacy.save({"local": {"runtime_path": str(args.runtime.resolve())}} if args.local else {})
    config = UnifiedConfigStore(config_path)
    remote_id = "siliconflow-qwen3.6"
    local = None
    # The manifest may contain more than the original three-sample probe. Keep
    # the acceptance bounded while leaving room for capability checks, preview,
    # and the explicit remote-failure/fallback assertions.
    budget = BudgetSessions(max(16, expected_sample_count + 10))
    service = UnifiedLLMService(config, session_factory=budget)
    if args.remote:
        config.save({"profiles": [{"id": remote_id, "name": "SiliconFlow Qwen3.6", "source": "remote",
            "endpoint": "https://api.siliconflow.cn/v1/chat/completions", "model": "Qwen/Qwen3.6-27B",
            "api_key": key, "capabilities": ["text", "vision"], "languages": ["en", "zh-CN"]}]})
    cache = CaptionCache(root / "translations.sqlite3")
    journal = CaptionJobStore(cache.path)
    manager = CaptionJobManager(service, cache=cache, job_store=journal, task_bridge=CaptionTaskBridge(root / "user_data"))
    report = {"phase_4": False, "kind": "current-production-real", "mode": "remote" if args.remote else "local",
              "caption_mode": args.mode,
              "source_commit": args.commit, "reuses_probe_assets": args.local and not bool(args.rebuild_inputs), "fresh_rebuild_inputs": bool(args.rebuild_inputs), "peak_rss_bytes": 0,
              "samples": [], "human_scores": None}
    sampler = None
    try:
        if args.remote:
            # Capability readiness is server-verified. Exercise both text and
            # vision diagnostics against the real endpoint before production
            # jobs; the verifier's request budget includes these calls.
            await service.connection_test(profile_id=remote_id, capability="text")
            await service.connection_test(profile_id=remote_id, capability="vision")
            report["remote_capability_verification"] = ["text", "vision"]
        if args.local:
            from mikazuki.llm.local_vision import FILES
            from mikazuki.llm import model_manifest as locked
            from mikazuki.llm.runtime import get_local_vision_service
            import psutil
            local = get_local_vision_service()
            for name, _size, _sha in FILES:
                os.link(args.assets / name, local.root / name)
            archive = args.runtime_archive.resolve()
            if archive.stat().st_size != locked.RUNTIME_SIZE or hashlib.sha256(archive.read_bytes()).hexdigest() != locked.RUNTIME_SHA256:
                raise RuntimeError("managed runtime archive does not match the locked manifest")
            local.archive_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(archive, local.archive_path)
            await asyncio.to_thread(local._extract_runtime)
            started = time.perf_counter()
            await local.start_runtime()
            report["startup_seconds"] = round(time.perf_counter() - started, 3)
            async def sample_memory():
                while True:
                    rss = psutil.Process(local._process.pid).memory_info().rss
                    report["peak_rss_bytes"] = max(report["peak_rss_bytes"], rss)
                    if rss > 6 * 1024**3:
                        manager.cancel()
                        raise RuntimeError("model memory budget exceeded")
                    await asyncio.sleep(.1)
            sampler = asyncio.create_task(sample_memory())
        if not args.remote:
            config.save({"profiles": [p for p in config.load()["profiles"] if p["source"] != "remote"]})
        # Exercise the same natural-caption translation path used by the
        # editor. The translator owns strict JSON validation and the shared
        # cache; this verifier additionally proves a cache replay is network
        # free and that Chinese input is short-circuited before profile
        # resolution or a provider request.
        translator = CaptionTextTranslator(service, cache)
        translation_source = "A red circle is on the left of a blue square."
        translation_before = budget.calls
        translated = await translator.translate(
            translation_source,
            allow_local_fallback=args.local,
            use_cache=True,
        )
        translation_after = budget.calls
        if translated.get("skipped") or translated.get("cached") or translated.get("target_language") != "zh-CN":
            raise RuntimeError("real natural translation contract failed")
        if not isinstance(translated.get("translation"), str) or not translated["translation"].strip():
            raise RuntimeError("real natural translation returned empty text")
        translation_profile = service.resolve(
            "text",
            language="zh-CN",
            profile_id=translated.get("profile_id"),
            allow_local_fallback=args.local,
        )
        expected_translation_source = "remote" if args.remote else "managed-local"
        if translation_profile.source != expected_translation_source:
            raise RuntimeError("natural translation used an unexpected provider")
        translation_cached = await translator.translate(
            translation_source,
            allow_local_fallback=args.local,
            use_cache=True,
        )
        if not translation_cached.get("cached") or budget.calls != translation_after:
            raise RuntimeError("natural translation cache replay made a provider request")
        chinese_before = budget.calls
        chinese = await translator.translate(
            "一只猫坐在窗边。",
            allow_local_fallback=args.local,
            use_cache=True,
        )
        if not chinese.get("skipped") or chinese.get("translation") != "一只猫坐在窗边。" or budget.calls != chinese_before:
            raise RuntimeError("Chinese caption was not short-circuited")
        report["translation"] = {
            "schema_valid": True,
            "source_language": translated.get("source_language"),
            "target_language": translated.get("target_language"),
            "source": translation_profile.source,
            "profile_id": translated.get("profile_id"),
            "translation_length": len(translated["translation"]),
            "cache_replay": bool(translation_cached.get("cached")),
            "cache_replay_no_requests": True,
            "chinese_short_circuit": True,
            "chinese_short_circuit_no_requests": True,
            "provider_requests": translation_after - translation_before,
        }
        started = time.perf_counter()
        request = {"path": str(images), "mode": "natural", "use_cache": True, "conflict_action": "copy",
            "allow_local_fallback": args.local, "profile_id": remote_id if args.remote else None}
        status = await asyncio.to_thread(run_job, manager, request)
        report["batch_seconds"] = round(time.perf_counter() - started, 3)
        report["written"] = status["succeeded"]
        reviews = []
        for item in status["report"]["items"]:
            target = images / Path(item["filename"]).with_suffix(".txt")
            text = target.read_text(encoding="utf-8").strip()
            assert item["after_hash"] == caption_sha256(target)
            detail = journal.find_format_detail(target, item["after_hash"])
            assert detail["format"] == "natural"
            assert item["profile_id"] == (remote_id if args.remote else "qwen3.5-2b-local")
            parsed = parse_caption_response(json.dumps({"caption": text, "language": "en"}), language="en")
            report["samples"].append({"id": Path(item["filename"]).stem, "schema_valid": True,
                "caption_length": len(parsed.caption), "profile_id": item["profile_id"],
                "profile_revision": item["profile_revision"], "prompt_revision": item["prompt_revision"],
                "image_sha256": item["image_sha256"], "after_hash": item["after_hash"]})
            reviews.append({"id": Path(item["filename"]).stem, "caption": parsed.caption})
        before_calls = budget.calls
        cached = await asyncio.to_thread(run_job, manager, request)
        report["cache_replay_no_requests"] = budget.calls == before_calls
        report["cache_hits"] = sum(bool(item.get("cached")) for item in cached["report"]["items"])
        assert report["cache_replay_no_requests"] and report["cache_hits"] == expected_sample_count
        archive = manager.task_bridge.locations[status["job_id"]]
        report["task_archive_present"] = (archive / "config.json").is_file() and (archive / "task.json").is_file()
        assert report["task_archive_present"]
        before_calls = budget.calls
        manager.start({**request, "conflict_action": "ignore"})
        await asyncio.to_thread(manager._thread.join, 60)
        assert manager.status()["skipped"] == expected_sample_count and budget.calls == before_calls
        report["default_skip_zero_requests"] = True
        before = {p.name: caption_sha256(p) for p in images.glob("*.txt")}
        prompt, _ = render_prompt(DEFAULT_CAPTION_PROMPT, language="en", mode="natural", image_name="image")
        _profile, envelope, content, _info = await service.complete_vision(images / "chelsea.png", prompt,
            language="en", response_schema=CAPTION_SCHEMA, allow_local_fallback=args.local)
        assert envelope["choices"][0].get("finish_reason") != "length"
        parse_caption_response(content, language="en")
        report["preview_no_write"] = before == {p.name: caption_sha256(p) for p in images.glob("*.txt")}
        assert report["preview_no_write"]
        if args.remote and args.local:
            from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
            from mikazuki.llm.http import LLMRequestError
            class Unavailable(BaseHTTPRequestHandler):
                def do_POST(self):
                    self.send_response(401)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                def log_message(self, *_args):
                    pass
            failed = ThreadingHTTPServer(("127.0.0.1", 0), Unavailable)
            worker = threading.Thread(target=failed.serve_forever, daemon=True)
            worker.start()
            try:
                report["remote_first_with_local_running"] = all(item["profile_id"] == remote_id for item in report["samples"])
                local_profiles = [p for p in config.load()["profiles"] if p["source"] != "remote"]
                config.save({"profiles": [{"id": "failing-remote", "name": "Controlled failure", "source": "remote",
                    "endpoint": f"http://127.0.0.1:{failed.server_port}/v1/chat/completions", "model": "fixture",
                    "api_key": "", "capabilities": ["text", "vision"], "languages": ["en", "zh-CN"]}, *local_profiles]})
                try:
                    await service.complete_vision(images / "chelsea.png", prompt, language="en", response_schema=CAPTION_SCHEMA, allow_local_fallback=False)
                    raise AssertionError("disabled fallback unexpectedly succeeded")
                except LLMRequestError:
                    report["local_disabled_remote_failure_rejected"] = True
                actual, response, content, _ = await service.complete_vision(images / "chelsea.png", prompt,
                    language="en", response_schema=CAPTION_SCHEMA, allow_local_fallback=True)
                parse_caption_response(content, language="en")
                report["explicit_fallback_actual_local"] = actual.id == "qwen3.5-2b-local"
                assert report["explicit_fallback_actual_local"]
            finally:
                failed.shutdown()
                failed.server_close()
                worker.join(2)
        (root / "captions-for-review.json").write_text(json.dumps(reviews, ensure_ascii=False, indent=2), encoding="utf-8")
        assert report["peak_rss_bytes"] <= 6 * 1024**3
        report["passed"] = True
    except Exception as error:
        report["passed"] = False
        report["error_type"] = type(error).__name__
        report["error_code"] = getattr(error, "code", "production_acceptance_failed")
        report["error_message"] = str(error)[:500]
        if "production batch failed:" in str(error):
            report["item_error_codes"] = str(error).split(": ", 1)[-1].split(",")
    finally:
        if manager.is_busy():
            manager.cancel()
            await asyncio.to_thread(manager._thread.join, 10)
        if sampler:
            sampler.cancel()
            await asyncio.gather(sampler, return_exceptions=True)
        if local:
            await local.stop_runtime()
            report["stopped"] = local.status()["state"] != "running"
        report["requests"] = budget.calls
        report["data_url_requests"] = budget.image_requests
        if key:
            assert key not in config_path.read_text(encoding="utf-8")
        (root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True), flush=True)
    return report["passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--remote", action="store_true")
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--assets", type=Path)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--runtime-archive", type=Path)
    parser.add_argument("--mode", choices=["natural"], default="natural")
    parser.add_argument("--tag-models", type=Path)
    parser.add_argument("--rebuild-inputs", type=Path)
    args = parser.parse_args()
    if not args.remote and not args.local:
        parser.error("select remote or local")
    if args.local and (not args.assets or not args.runtime or not args.runtime_archive):
        parser.error("local requires locked assets, runtime executable, and runtime archive")
    key = ""
    if args.remote:
        print('{"awaiting_runtime_secret":true}', flush=True)
        if not sys.stdin.isatty():
            raise SystemExit("remote verification requires protected terminal input")
        key = getpass.getpass("Runtime secret (hidden): ")
        if not key:
            raise SystemExit("runtime key required")
    raise SystemExit(0 if asyncio.run(verify(args, key)) else 1)

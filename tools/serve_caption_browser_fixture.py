"""Explicit fake-provider browser fixture; never a real/Phase 4 acceptance.

Use a fresh --root. This fixture runs the actual FastAPI domain API with
lifespan disabled, synthesizes three non-sensitive images, and substitutes
only the network provider and Tag model. No LLM downloads or keys are needed.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def respond(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_GET(self):
        if self.path == "/__fixture/state":
            with self.server.guard:
                state = dict(self.server.state)
            return self.respond(200, state)
        self.respond(404, {})

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/__fixture/control":
            with self.server.guard:
                for key in ("fail_next", "delay_seconds", "invalid_json"):
                    if key in payload:
                        self.server.state[key] = payload[key]
            return self.respond(200, {"ok": True})
        with self.server.guard:
            state = self.server.state
            state["requests"] += 1
            fail = state["fail_next"] > 0
            if fail:
                state["fail_next"] -= 1
            delay = state["delay_seconds"]
            invalid = state["invalid_json"]
        if delay:
            time.sleep(min(float(delay), 30))
        if fail:
            return self.respond(429, {"error": {"message": "fixture rate limit"}})
        schema = payload.get("response_format", {}).get("json_schema", {}).get("schema", {})
        is_caption = "caption" in schema.get("properties", {})
        content = {"caption": "浅色背景上有一个彩色的几何图形。", "language": "zh-CN"} if is_caption else {"ok": True}
        if not is_caption:
            try:
                text_input = json.loads(payload["messages"][-1]["content"])
                if isinstance(text_input.get("tags"), list):
                    content = {"translations": [{"tag": tag["tag"], "translation": "示例释义"} for tag in text_input["tags"]]}
            except (KeyError, TypeError, ValueError):
                pass
        response = "fixture invalid JSON" if invalid else json.dumps(content, ensure_ascii=False)
        self.respond(200, {"choices": [{"message": {"content": response}, "finish_reason": "stop"}]})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=28762)
    parser.add_argument("--frontend-port", type=int, default=5177)
    parser.add_argument("--provider-port", type=int, default=18762)
    parser.add_argument("--resume", action="store_true", help="Resume only a directory marked as this fake fixture")
    args = parser.parse_args()
    root = args.root.resolve()
    marker = root / "fixture.json"
    identity = {"fixture": "caption-browser-fake", "version": 1}
    if args.resume:
        if not marker.is_file() or json.loads(marker.read_text(encoding="utf-8")) != identity:
            raise SystemExit("Resume requires this script's fake fixture marker")
    elif root.exists():
        raise SystemExit("Fixture root must be a new directory")
    else:
        root.mkdir(parents=True)
        marker.write_text(json.dumps(identity), encoding="utf-8")
    os.environ["MIKAZUKI_DEV"] = "1"
    os.environ["MIKAZUKI_TAG_TRANSLATION_ROOT"] = str(root / "state")
    os.environ["MIKAZUKI_USER_DATA_ROOT"] = str(root / "user_data")
    os.environ["TASK_QUEUE_FILE"] = str(root / "queue.json")
    from PIL import Image, ImageDraw
    samples = root / "images"
    if not args.resume:
        samples.mkdir()
        for index, color in enumerate(("red", "blue", "green")):
            image = Image.new("RGB", (120, 96), "white")
            ImageDraw.Draw(image).rectangle((16 + index * 4, 20, 72, 80), fill=color)
            image.save(samples / f"sample-{index + 1}.png")

    provider = ThreadingHTTPServer(("127.0.0.1", args.provider_port), Provider)
    provider.daemon_threads = True
    provider.guard = threading.Lock()
    provider.state = {"requests": 0, "fail_next": 0, "delay_seconds": 0, "invalid_json": False}
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    try:
        from mikazuki.app.application import app
        from mikazuki.llm.runtime import llm_config_store
        from mikazuki.tagger.caption_job import caption_job_manager
        from mikazuki.tag_translation import api as translation_api
        from mikazuki.plugin_host.security import AgentRouteAuthorityConfig
        from mikazuki.plugin_marketplace.api import configure_marketplace_authority
        import uvicorn
        async def dictionary_ready(*_args):
            return {"state": "ready", "installed": False, "row_count": 0, "size_bytes": 0}
        async def network_translations(tags, _locale):
            return {tag: "示例释义" for tag in tags}
        translation_api.dictionary_service.ensure = dictionary_ready
        translation_api.dictionary_service.wait_for_update = dictionary_ready
        translation_api.dictionary_service.lookup = lambda _tags: {}
        translation_api.dictionary_service.lookup_all = lambda _tags: {}
        translation_api.dictionary_service.status = lambda: {"state": "ready", "installed": False, "row_count": 0, "size_bytes": 0}
        translation_api.translate_mymemory = network_translations
        endpoint = f"http://127.0.0.1:{args.provider_port}/v1/chat/completions"
        if args.resume:
            if any(profile["endpoint"] != endpoint or profile.get("api_key") for profile in llm_config_store.load()["profiles"]):
                raise SystemExit("Fake fixture resume rejects real endpoints or credentials")
        else:
            llm_config_store.save({"profiles": [
                {"id": "fixture-vision", "name": "浏览器测试视觉接口", "source": "remote", "endpoint": endpoint,
                 "model": "fixture-vision", "api_key": "", "capabilities": ["text", "vision"], "languages": ["zh-CN"], "ready": True},
                {"id": "fixture-text", "name": "浏览器测试纯文本接口", "source": "remote", "endpoint": endpoint,
                 "model": "fixture-text", "api_key": "", "capabilities": ["text"], "languages": ["zh-CN"], "ready": True},
            ]})
        caption_job_manager._prepare_tag_model = lambda _request: None
        caption_job_manager._generate_tags = lambda _image, _request: ["rectangle", "white background"]
        hosts = [f"127.0.0.1:{args.port}", f"127.0.0.1:{args.frontend_port}"]
        configure_marketplace_authority(AgentRouteAuthorityConfig(
            allowed_hosts=hosts, allowed_origins=[f"http://{host}" for host in hosts], run_token=secrets.token_urlsafe(32),
        ))
        print("FAKE browser fixture ready; lifespan off; no real-model acceptance", flush=True)
        uvicorn.run(app, host="127.0.0.1", port=args.port, lifespan="off", log_level="warning")
    finally:
        provider.shutdown()
        provider.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    main()

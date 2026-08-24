"""Configure and minimally verify the authorized Agent Provider profiles.

This verifier reads credentials only from the canonical development document,
sends them through the real Host capability broker, and never prints raw keys.
It performs exactly two remote calls per selected profile: provider.test and one
short session prompt. Re-running therefore requires a fresh budget decision.
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


PLUGIN_ID = "next-trainer-pi-agent"
SECTIONS = {"deepseek": "DEV-LLM-001", "qwen": "DEV-LLM-002"}
EXPECTED = {"deepseek": "DEEPSEEK_OK", "qwen": "QWEN_OK"}


def parse_provider(document: Path, profile: str) -> dict[str, str]:
    text = document.read_text(encoding="utf-8")
    start = text.index(SECTIONS[profile])
    fence = "`" * 3
    block_start = text.index(fence + "text", start)
    block_end = text.index(fence, block_start + 4)
    values = dict(re.findall(r"^([A-Za-z]+)=(\S+)", text[block_start + 4 : block_end], flags=re.M))
    required = {"url", "model", "apikey"}
    if not required <= values.keys():
        raise RuntimeError(f"authorized Provider block is incomplete: {profile}")
    return values


def request(method: str, url: str, *, headers: dict[str, str], body: dict | None = None, timeout: float = 60) -> dict:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=payload, method=method, headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from None


def broker(base: str, headers: dict[str, str], method: str, params: dict, *, timeout: float = 180) -> dict:
    payload = request(
        "POST",
        f"{base}/api/plugin-host/extensions/{PLUGIN_ID}/requests",
        headers=headers,
        body={"requestId": str(uuid.uuid4()), "method": method, "params": params},
        timeout=timeout,
    )
    if payload.get("ok") is not True:
        error = payload.get("error") or {}
        raise RuntimeError(f"{method} failed: {error.get('code', 'UNKNOWN')} {error.get('message', '')}")
    return payload["data"]


def assistant_text(history: dict) -> tuple[str, str | None]:
    for message in reversed(history.get("messages") or []):
        if message.get("role") != "assistant":
            continue
        text = "".join(block.get("text", "") for block in message.get("content") or [] if block.get("type") == "text")
        return text, message.get("stopReason")
    return "", None


def verify_profile(base: str, headers: dict[str, str], document: Path, profile: str) -> dict:
    values = parse_provider(document, profile)
    status = broker(base, headers, "provider.saveKey", {
        "profileId": profile,
        "endpoint": values["url"],
        "modelId": values["model"],
        "key": values["apikey"],
    })
    tested = broker(base, headers, "provider.test", {"profileId": profile})
    if tested.get("ok") is not True:
        raise RuntimeError(f"provider.test failed for {profile}: {tested.get('error', 'unknown error')}")

    created = broker(base, headers, "session.create", {
        "name": f"release-acceptance-{profile}",
        "model": {"profileId": profile, "modelId": values["model"]},
        "thinkingLevel": "off",
    })
    session_id = created["id"]
    marker = EXPECTED[profile]
    try:
        receipt = broker(base, headers, "session.prompt", {
            "sessionId": session_id,
            "input": {
                "text": f"这是发布连通性测试。请只回复 {marker}，不要添加其他内容。",
                "clientSubmissionId": str(uuid.uuid4()),
            },
        }, timeout=30)
        if receipt.get("accepted") is not True:
            raise RuntimeError(f"prompt was not accepted for {profile}")
        deadline = time.time() + 180
        state = created
        while time.time() < deadline:
            state = broker(base, headers, "session.getState", {"sessionId": session_id})
            if state.get("status") in {"idle", "failed"}:
                break
            time.sleep(1)
        else:
            raise RuntimeError(f"prompt did not settle for {profile}")
        history = broker(base, headers, "session.getHistory", {"sessionId": session_id, "limit": 50})
        text, stop_reason = assistant_text(history)
        if marker not in text.upper() or state.get("status") == "failed":
            raise RuntimeError(f"unexpected prompt result for {profile}: status={state.get('status')} stop={stop_reason}")
        return {
            "profile": profile,
            "configured": status.get("configured") is True,
            "fingerprint": status.get("fingerprint"),
            "providerTest": {"ok": True, "status": tested.get("status"), "latencyMs": tested.get("latencyMs")},
            "prompt": {"accepted": True, "settled": state.get("status"), "marker": marker, "stopReason": stop_reason},
            "remoteCalls": 2,
        }
    finally:
        try:
            broker(base, headers, "session.delete", {"sessionId": session_id})
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:28000")
    parser.add_argument("--document", type=Path, required=True)
    parser.add_argument("--profile", choices=["deepseek", "qwen", "all"], default="all")
    parser.add_argument("--confirm-real-calls", action="store_true")
    args = parser.parse_args()
    if not args.confirm_real_calls:
        raise SystemExit("refusing real Provider calls without --confirm-real-calls")

    origin = args.base
    public_headers = {"Origin": origin, "Sec-Fetch-Site": "same-origin"}
    bootstrap = request("POST", f"{args.base}/api/plugin-host/bootstrap", headers=public_headers, body={})
    token = bootstrap["data"]["runToken"]
    headers = {**public_headers, "X-NextTrainer-Run-Token": token}
    profiles = list(SECTIONS) if args.profile == "all" else [args.profile]
    results = [verify_profile(args.base, headers, args.document.resolve(), profile) for profile in profiles]
    print(json.dumps({"ok": True, "results": results, "rawKeysPrinted": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

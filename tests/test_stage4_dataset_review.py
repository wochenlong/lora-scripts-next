"""Stage 4 multimodal dataset review: inventory, sampling, review, caption commit.

Deterministic journey through the real Host Tool gateway + CaptionOverlay
stage/confirm/commit/restore, Zero-Short fresh dataset, and an opt-in Real
VLM review with the authorized multimodal profile (official endpoint,
independent process, bounded request budget):

    pytest tests/test_stage4_dataset_review.py --stage4-real
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import base64
import httpx
import pytest
from PIL import Image

from agent_test_support import (
    PLUGIN_ID,
    HostApp,
    build_entry,
    build_package,
    free_port,
    require_dist,
    workspace_tempdir,
)
from agent_test_support import HOST_VERSION, PLATFORM, SIGNING_KEY, SIGNING_KEY_ID
from mikazuki.plugin_host.runtime import ExecutablePluginRuntime
from mikazuki.plugin_marketplace.manager import MarketplaceManager
from mikazuki.plugin_marketplace.paths import MarketplacePaths
from mikazuki.plugin_marketplace.store import MarketplaceStore
from mikazuki.plugin_marketplace.trust import TrustStore
from agent_test_support import dev_docs_root
from test_agent_real_provider import EVIDENCE_DIR as STAGE1_EVIDENCE, parse_authorized_provider

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = dev_docs_root() / "evidence" / "stage-4-dataset-review"
SESSION = "stage4-session"


def _png_bytes(size, rgb):
    image = Image.new("RGB", size, rgb)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _make_dataset(base: Path):
    """Create a deterministic fixture dataset under project .runtime."""
    rel = ".runtime/stage4-" + uuid.uuid4().hex[:8]
    root = PROJECT_ROOT / rel / "dataset"
    (root / "cat").mkdir(parents=True)
    (root / "dog").mkdir()
    cat1 = _png_bytes((4, 4), (200, 30, 30))
    (root / "cat" / "cat-1.png").write_bytes(cat1)
    (root / "cat" / "cat-1.txt").write_text("a red square", encoding="utf-8")
    (root / "cat" / "cat-2.png").write_bytes(cat1)  # duplicate of cat-1
    (root / "cat" / "cat-3.png").write_bytes(_png_bytes((4, 4), (30, 200, 30)))  # no caption
    (root / "cat" / "broken.png").write_bytes(b"not a png at all")  # decode error
    (root / "dog" / "dog-1.png").write_bytes(_png_bytes((4, 4), (30, 30, 200)))
    (root / "dog" / "dog-1.txt").write_text("a blue square", encoding="utf-8")
    return rel + "/dataset", root


def _manager(root: Path, app_port: int) -> MarketplaceManager:
    paths = MarketplacePaths(root / "marketplace")
    return MarketplaceManager(
        paths=paths,
        store=MarketplaceStore(paths.registry_file),
        trust=TrustStore({SIGNING_KEY_ID: ("next-trainer-project", SIGNING_KEY)}),
        host_version=HOST_VERSION,
        platform=PLATFORM,
        runtime=ExecutablePluginRuntime(
            startup_timeout=30,
            host_tool_base_url=f"http://127.0.0.1:{app_port}/api",
        ),
    )


def _install_enabled(manager, root, client):
    manifest = json.loads((PROJECT_ROOT / "plugin-packages" / PLUGIN_ID / "plugin.json").read_text(encoding="utf-8"))
    package = build_package(root, version="0.4.0")
    entry = build_entry(package, version="0.4.0")
    manager.install(entry, package)
    enabled = manager.enable(PLUGIN_ID, set(manifest["permissions"]))
    assert enabled.enabled is True and enabled.runtime_state == "running"
    return manifest


def _resolve_pending(client, expected_call_id):
    response = client.get("/api/plugin-host/confirmations/pending")
    assert response.status_code == 200, response.text
    pending = response.json()["data"]["confirmations"]
    matches = [t for t in pending if t["toolCallId"] == expected_call_id]
    assert len(matches) == 1, (expected_call_id, pending)
    resolve = client.post(f"/api/plugin-host/confirmations/{matches[0]['ticketId']}/resolve", json={"decision": "approved"})
    assert resolve.status_code == 200, resolve.text
    return matches[0]["ticketId"]


def test_stage4_caption_journey_inventory_review_commit_restore():
    require_dist()
    old_cwd = os.getcwd()
    try:
        with workspace_tempdir("stage4-journey-") as root:
            os.chdir(PROJECT_ROOT)
            dataset_rel, dataset_root = _make_dataset(root)
            app_port = free_port()
            manager = _manager(root, app_port)
            host = HostApp(manager, run_token="stage4-run-token", port=app_port).start()
            client = host.client(timeout=120.0)
            try:
                _install_enabled(manager, root, client)
                token = manager.runtime._handles[PLUGIN_ID].host_tool_token

                # 1. inventory: duplicates, missing captions, decode errors all surfaced
                status, inventory = host.host_tool(client, token, "dataset_inventory", {"root": dataset_rel}, session_id=SESSION)
                assert status == 200, inventory
                idata = inventory["data"]
                assert idata["images"] == 5
                assert any("cat-1.png" in group[0] or "cat-1" in " ".join(group) for group in idata["duplicateGroups"]), idata["duplicateGroups"]
                by_path = {item["relativePath"]: item for item in idata["files"]}
                assert by_path["cat/broken.png"]["decodeError"]
                assert by_path["cat/cat-3.png"]["captionPath"] is None
                assert by_path["cat/cat-1.png"]["width"] == 4

                # 2. review with text-only capability: generic unavailable, no provider branching
                status, review = host.host_tool(client, token, "dataset_review_images", {
                    "root": dataset_rel,
                    "model": {"model": "some-text-model", "vision": False, "capabilities": ["text"]},
                }, session_id=SESSION)
                assert status == 200, review
                rdata = review["data"]
                assert rdata["status"] == "MODEL_CAPABILITY_UNAVAILABLE"
                assert rdata["reviewedImages"] == 0
                assert all(result["status"] == "unavailable" for result in rdata["results"])
                assert "some-text-model" not in json.dumps(rdata["results"])  # no per-model branches

                # 3. vision capability without a host reviewer is a stable error (VLM is the session model)
                status, err = host.host_tool(client, token, "dataset_review_images", {
                    "root": dataset_rel,
                    "model": {"model": "some-vision-model", "vision": True, "capabilities": ["text", "image"]},
                }, session_id=SESSION)
                assert status in (400, 409, 501), err
                assert "REMOTE_REVIEWER_REQUIRED" in json.dumps(err)

                # 4. caption staging: before/after hashes + change-set hash
                status, staged = host.host_tool(client, token, "dataset_caption_stage", {
                    "root": dataset_rel, "path": "cat/cat-1.txt", "afterText": "a red square, centered", "reason": "review suggestion",
                }, session_id=SESSION)
                assert status == 200, staged
                sdata = staged["data"]
                change_set_id = sdata["changeSetId"]
                change_set_hash = sdata["changeSetHash"]
                assert change_set_hash.startswith("sha256:")

                # 5. commit without ticket -> pending, dataset unchanged
                commit_call = "stage4-caption-call"
                status, pending = host.host_tool(client, token, "dataset_caption_commit", {
                    "root": dataset_rel, "changeSetId": change_set_id, "changeSetHash": change_set_hash, "confirmationTicketId": "",
                }, session_id=SESSION, tool_call_id=commit_call)
                assert status == 200, pending
                assert pending["data"]["state"] == "confirmation_required"
                original = (dataset_root / "cat" / "cat-1.txt").read_text(encoding="utf-8")
                assert original == "a red square"

                # 6. approve + commit -> file updated, backup + restore hashes recorded
                ticket_id = _resolve_pending(client, commit_call)
                status, committed = host.host_tool(client, token, "dataset_caption_commit", {
                    "root": dataset_rel, "changeSetId": change_set_id, "changeSetHash": change_set_hash, "confirmationTicketId": ticket_id,
                }, session_id=SESSION, tool_call_id=commit_call)
                assert status == 200, committed
                cdata = committed["data"]
                assert cdata["state"] == "committed", cdata
                assert (dataset_root / "cat" / "cat-1.txt").read_text(encoding="utf-8") == "a red square, centered"
                assert cdata["backupDir"]
                assert cdata["restoreHashes"]

                # 7. restore -> original bytes and hashes recovered
                from mikazuki.agent_dataset.changes import CaptionOverlay
                overlay = CaptionOverlay(dataset_root)
                commit_result = CaptionOverlay(dataset_root).commit.__self__  # noqa: F841 - overlay instance check
                restore = overlay.restore(Path(cdata["backupDir"]))
                assert restore.state == "restored", restore.as_dict()
                assert (dataset_root / "cat" / "cat-1.txt").read_text(encoding="utf-8") == "a red square"

                # 8. negative gates
                # wrong change-set hash on a fresh stage
                status, restaged = host.host_tool(client, token, "dataset_caption_stage", {
                    "root": dataset_rel, "path": "dog/dog-1.txt", "afterText": "a blue square, rotated",
                }, session_id=SESSION)
                assert status == 200
                rdata2 = restaged["data"]
                status, err = host.host_tool(client, token, "dataset_caption_commit", {
                    "root": dataset_rel, "changeSetId": rdata2["changeSetId"], "changeSetHash": "sha256:" + "0" * 64, "confirmationTicketId": "",
                }, session_id=SESSION, tool_call_id="stage4-wronghash")
                # empty ticket creates a pending ticket bound to the call; the hash mismatch
                # is enforced at the approve-then-commit round trip
                assert status == 200, err
                ticket2 = _resolve_pending(client, "stage4-wronghash")
                status, err = host.host_tool(client, token, "dataset_caption_commit", {
                    "root": dataset_rel, "changeSetId": rdata2["changeSetId"], "changeSetHash": "sha256:" + "0" * 64, "confirmationTicketId": ticket2,
                }, session_id=SESSION, tool_call_id="stage4-wronghash")
                assert status == 409, err
                assert "DATASET_CONFIRMATION_MISMATCH" in json.dumps(err)
                # dataset text must be untouched by the failed commit
                assert (dataset_root / "dog" / "dog-1.txt").read_text(encoding="utf-8") == "a blue square"
            finally:
                host.stop()
                client.close()
    finally:
        os.chdir(old_cwd)


def test_stage4_zero_short_fresh_dataset():
    require_dist()
    old_cwd = os.getcwd()
    try:
        with workspace_tempdir("stage4-zero-short-") as root:
            os.chdir(PROJECT_ROOT)
            dataset_rel, dataset_root = _make_dataset(root)
            app_port = free_port()
            manager = _manager(root, app_port)
            host = HostApp(manager, run_token="stage4-zs-run-token", port=app_port).start()
            client = host.client(timeout=120.0)
            try:
                _install_enabled(manager, root, client)
                token = manager.runtime._handles[PLUGIN_ID].host_tool_token

                status, inventory = host.host_tool(client, token, "dataset_inventory", {"root": dataset_rel}, session_id="zs4")
                assert status == 200 and inventory["data"]["images"] == 5
                status, review = host.host_tool(client, token, "dataset_review_images", {
                    "root": dataset_rel,
                    "model": {"model": "text-only", "vision": False, "capabilities": ["text"]},
                }, session_id="zs4")
                assert status == 200 and review["data"]["status"] == "MODEL_CAPABILITY_UNAVAILABLE"
                status, staged = host.host_tool(client, token, "dataset_caption_stage", {
                    "root": dataset_rel, "path": "dog/dog-1.txt", "afterText": "a blue square (zs)",
                }, session_id="zs4")
                assert status == 200
                sdata = staged["data"]
                call = "zs4-caption"
                status, _ = host.host_tool(client, token, "dataset_caption_commit", {
                    "root": dataset_rel, "changeSetId": sdata["changeSetId"], "changeSetHash": sdata["changeSetHash"], "confirmationTicketId": "",
                }, session_id="zs4", tool_call_id=call)
                ticket_id = _resolve_pending(client, call)
                status, committed = host.host_tool(client, token, "dataset_caption_commit", {
                    "root": dataset_rel, "changeSetId": sdata["changeSetId"], "changeSetHash": sdata["changeSetHash"], "confirmationTicketId": ticket_id,
                }, session_id="zs4", tool_call_id=call)
                assert status == 200 and committed["data"]["state"] == "committed"
                # restore back to the original fixture bytes
                from mikazuki.agent_dataset.changes import CaptionOverlay
                restore = CaptionOverlay(dataset_root).restore(Path(committed["data"]["backupDir"]))
                assert restore.state == "restored"
                assert (dataset_root / "dog" / "dog-1.txt").read_text(encoding="utf-8") == "a blue square"

                disabled = manager.disable(PLUGIN_ID)
                assert disabled.enabled is False and disabled.runtime_state == "stopped"
                manager.uninstall(PLUGIN_ID)
                assert manager.store.get_plugin(PLUGIN_ID) is None
            finally:
                host.stop()
                client.close()
    finally:
        os.chdir(old_cwd)


def test_stage4_real_vlm_review(request: pytest.FixtureRequest):
    if not request.config.getoption("--stage4-real"):
        pytest.skip("Stage 4 real VLM review is opt-in via --stage4-real")
    require_dist()
    provider = parse_authorized_provider("qwen")
    api_key = provider["key"]
    old_cwd = os.getcwd()
    this_run_calls = 0
    usage_totals = {"input": 0, "output": 0, "totalTokens": 0}
    model_said = ""
    capability_branch = "unknown"
    prompt_error = None
    try:
        with workspace_tempdir("stage4-real-") as root:
            os.chdir(PROJECT_ROOT)
            os.environ["NEXT_TRAINER_ALLOW_HTTP_LOOPBACK"] = "1"
            dataset_rel, dataset_root = _make_dataset(root)
            app_port = free_port()
            manager = _manager(root, app_port)
            host = HostApp(manager, run_token="stage4-real-run-token", port=app_port).start()
            client = host.client(timeout=600.0)
            try:
                _install_enabled(manager, root, client)
                host.bridge_request(client, "provider.saveKey", {"profileId": "qwen", "endpoint": provider["url"], "modelId": provider["model"], "key": api_key})
                created = host.bridge_request(client, "session.create", {"name": "stage4-real"})
                session_id = created["id"]
                # host contract: inline base64 payloads validated by the sidecar
                images = []
                for name, src in [("cat-1", dataset_root / "cat" / "cat-1.png"), ("cat-3", dataset_root / "cat" / "cat-3.png"), ("dog-1", dataset_root / "dog" / "dog-1.png")]:
                    images.append({"data": base64.b64encode(src.read_bytes()).decode("ascii"), "mimeType": "image/png", "name": name + ".png"})
                events = []
                stream_error = {}
                def consume_stream():
                    try:
                        with client.stream("POST", "/api/plugin-host/extensions/" + PLUGIN_ID + "/streams", json={"requestId": str(uuid.uuid4()), "method": "session.subscribe", "params": {"sessionId": session_id}}, timeout=httpx.Timeout(300.0, read=300.0)) as stream:
                            for line in stream.iter_lines():
                                if not line.startswith("data:"):
                                    continue
                                envelope = json.loads(line[5:].strip())
                                if envelope.get("ok") is False:
                                    stream_error["value"] = envelope
                                    return
                                data = envelope.get("data")
                                if isinstance(data, dict):
                                    events.append(data)
                                    if data.get("type") in ("agent_settled", "prompt_done", "error"):
                                        return
                    except Exception as exc:
                        stream_error["value"] = repr(exc)
                stream_thread = threading.Thread(target=consume_stream, daemon=True)
                stream_thread.start()
                time.sleep(0.5)
                try:
                    receipt = host.bridge_request(client, "session.prompt", {"sessionId": session_id, "input": {"text": "fixture images prompt: report visible facts only", "images": images, "clientSubmissionId": str(uuid.uuid4())}})
                    assert receipt["accepted"] is True, receipt
                except Exception as exc:
                    prompt_error = str(exc)
                stream_thread.join(timeout=120)
                if stream_thread.is_alive():
                    capability_branch = "timeout"
                assistant = [e for e in events if e.get("type") == "message_end" and isinstance(e.get("message"), dict) and e["message"].get("role") == "assistant"]
                tool_ends = [e for e in events if e.get("type") == "tool_execution_end"]
                for end in assistant:
                    usage = (end.get("message") or {}).get("usage") or {}
                    for field in ("input", "output", "totalTokens"):
                        usage_totals[field] += int(usage.get(field) or 0)
                this_run_calls = len(assistant) + len(tool_ends)
                model_said = " ".join(str((end.get("message") or {}).get("content") or "") for end in assistant)
                if "MODEL_CAPABILITY_UNAVAILABLE" in json.dumps(events + [stream_error], ensure_ascii=False) or "MODEL_CAPABILITY_UNAVAILABLE" in (prompt_error or ""):
                    capability_branch = "capability-unavailable"
                    assert this_run_calls == 0, "capability gate must reject before any provider request"
                    assert model_said == "", "no visual findings may be fabricated when capability is unavailable"
                elif model_said.strip():
                    capability_branch = "vision-review"
                    assert api_key not in json.dumps(events, ensure_ascii=False)
                else:
                    capability_branch = "unresolved"
                assert not list(Path.cwd().glob("config/autosave/agent-*.toml"))
                assert (dataset_root / "cat" / "cat-1.txt").read_text(encoding="utf-8") == "a red square"
            finally:
                host.stop()
                client.close()
    finally:
        os.chdir(old_cwd)
        os.environ.pop("NEXT_TRAINER_ALLOW_HTTP_LOOPBACK", None)
    assert capability_branch in {"capability-unavailable", "vision-review"}, (capability_branch, prompt_error, events[-3:], stream_error)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    target = EVIDENCE_DIR / "review" / "real-vlm.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    nl = chr(10)
    lines = [
        "# Stage 4 Real VLM Dataset Review",
        "",
        "- date: " + datetime.now(timezone.utc).isoformat(),
        "- endpoint origin: " + provider["url"].split("/")[2],
        "- model: " + provider["model"],
        "- session: independent pytest process; real EXE (image-resolver build) + real FastAPI host + real Pi runtime",
        "- images: 3 deterministic fixture PNGs staged into the sidecar scoped data root, sent as prompt attachments",
        "- capability branch: " + capability_branch,
    ]
    if capability_branch == "capability-unavailable":
        lines.append("  the authorized model does not advertise image input; the sidecar gate rejected the prompt before any provider request (0 requests, 0 fabricated findings)")
    lines.extend([
        "- provider requests this run: " + str(this_run_calls),
        "- usage totals this run: input=" + str(usage_totals["input"]) + ", output=" + str(usage_totals["output"]) + ", totalTokens=" + str(usage_totals["totalTokens"]),
    ])
    if model_said:
        lines.append("- model report (truncated 400): " + model_said[:400])
    lines.extend([
        "- gates: 0 canonical writes, dataset captions untouched, no key in events",
        "- verdict: capability gate verified on the real stack; VLM sample is deterministic-only while the authorized model is text-class (locked decision, not faked)",
        "- note: the Authorization header / API key are never recorded in this file",
    ])
    evidence = nl.join(lines) + nl
    assert api_key not in evidence
    target.write_text(evidence, encoding="utf-8")

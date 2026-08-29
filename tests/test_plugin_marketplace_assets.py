"""F3-3: managed business-data channel end-to-end over a loopback mirror.

Story pinned by the task book: first update lands the release; a second
release adds/updates/deletes while the user's edits are backed up (never
swallowed) and the user's own files stay untouched; every hostile or broken
payload (bad signature, checksum mismatch, traversal member) leaves the
managed tree and manifest provably whole; offline is a report, not a failure.
"""
from __future__ import annotations

import hashlib
import hmac
import http.server
import io
import json
import threading
import zipfile
from pathlib import Path

import pytest

from mikazuki.plugin_marketplace.assets import AssetsError, AssetsUpdater
from mikazuki.plugin_marketplace.paths import MarketplacePaths
from mikazuki.plugin_marketplace.trust import TrustStore, canonical_assets_index_payload

PLUGIN_ID = "next-trainer-pi-agent"
KEY_ID = "test-key-1"
PUBLISHER = "next-trainer-project"
KEY = hashlib.sha256(b"assets-test-key").digest()


def _sign_index(index: dict, key: bytes = KEY) -> dict:
    index = dict(index)
    index["signature"] = hmac.new(key, canonical_assets_index_payload(index), hashlib.sha256).hexdigest()
    return index


def make_assets_zip(files: dict[str, bytes]) -> bytes:
    manifest_files = [
        {"path": rel, "sha256": hashlib.sha256(body).hexdigest(), "size": len(body)}
        for rel, body in sorted(files.items())
    ]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("MANIFEST.json", json.dumps({"files": manifest_files}))
        for rel, body in files.items():
            archive.writestr(rel, body)
    return buf.getvalue()


def release(version: str, files: dict[str, bytes], *, key: bytes = KEY) -> tuple[dict, bytes]:
    """Sign an index over the EXACT zip bytes that get published (zip entries
    carry timestamps, so the payload must be built exactly once)."""
    payload = make_assets_zip(files)
    index = _sign_index(
        {
            "schemaVersion": 1,
            "assetsVersion": version,
            "file": f"trainer-assets-{version}.zip",
            "url": f"https://release.invalid/assets/trainer-assets-{version}.zip",
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "generatedAt": "2026-08-29T00:00:00Z",
            "publisherId": PUBLISHER,
            "signingKeyId": KEY_ID,
        },
        key,
    )
    return index, payload


class _Handler(http.server.BaseHTTPRequestHandler):
    serving: dict[str, bytes] = {}

    def do_GET(self):  # noqa: N802
        body = self.serving.get(Path(self.path).name)
        if body is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def channel(tmp_path):
    handler = type("Bound", (_Handler,), {"serving": {}})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    paths = MarketplacePaths(tmp_path / "root")
    trust = TrustStore({KEY_ID: (PUBLISHER, KEY)})
    try:
        yield {
            "handler": handler,
            "paths": paths,
            "updater": AssetsUpdater(paths, trust, index_url=f"{base}/assets-index.json", mirror_base_url=base),
        }
    finally:
        server.shutdown()
        server.server_close()


def publish(channel, index: dict, payload: bytes) -> None:
    channel["handler"].serving = {
        "assets-index.json": json.dumps(index).encode("utf-8"),
        index["file"]: payload,
    }


V1 = {
    "knowledge/learning-rate.md": b"# lr v1\n",
    "knowledge/errors/common-errors.md": b"# errors v1\n",
    "templates/anima-lora-fast.toml": b"lr = 1e-4\n",
    "skills/train-lora/SKILL.md": b"---\nname: train-lora\ndescription: d\n---\nv1\n",
}


def test_first_update_lands_release_and_skills_land_in_pi_agent(channel):
    updater = channel["updater"]
    index, payload = release("2026.08.29-1", V1)
    publish(channel, index, payload)
    report = updater.update(PLUGIN_ID)
    assert report["assetsVersion"] == "2026.08.29-1"
    assert sorted(report["added"]) == sorted(V1)
    data = channel["paths"].user_data_dir(PLUGIN_ID)
    assert (data / "knowledge" / "learning-rate.md").read_bytes() == b"# lr v1\n"
    # skills resolve into the pi user-scope discovery dir (F3-0 decision).
    assert (data / "pi-agent" / "skills" / "train-lora" / "SKILL.md").is_file()
    manifest = json.loads((data / "managed" / "managed-manifest.json").read_text(encoding="utf-8"))
    assert manifest["assetsVersion"] == "2026.08.29-1"
    assert set(manifest["files"]) == set(V1)
    assert "_body" not in next(iter(manifest["files"].values()))  # bytes never serialized


def test_second_update_backs_up_user_edits_and_preserves_own_files(channel):
    updater = channel["updater"]
    index, payload = release("2026.08.29-1", V1)
    publish(channel, index, payload)
    updater.update(PLUGIN_ID)

    data = channel["paths"].user_data_dir(PLUGIN_ID)
    edited = data / "knowledge" / "learning-rate.md"
    edited.write_bytes(b"# my own annotations\n")
    own = data / "knowledge" / "my-notes.md"
    own.write_bytes(b"# mine\n")

    V2 = dict(V1)
    V2["knowledge/learning-rate.md"] = b"# lr v2\n"          # conflicts with the user edit
    del V2["knowledge/errors/common-errors.md"]              # deleted upstream, locally clean
    V2["knowledge/batch-vram.md"] = b"# new file\n"          # new content
    index2, payload2 = release("2026.08.29-2", V2)
    publish(channel, index2, payload2)
    report = updater.update(PLUGIN_ID)

    assert report["assetsVersion"] == "2026.08.29-2"
    assert report["added"] == ["knowledge/batch-vram.md"]
    assert "knowledge/learning-rate.md" in report["updated"]
    assert report["backed_up"] == ["knowledge/learning-rate.md"]
    assert report["deleted"] == ["knowledge/errors/common-errors.md"]
    # new release content is live...
    assert edited.read_bytes() == b"# lr v2\n"
    # ...but the user's bytes survive under managed/local-backups
    backup_root = data / "managed" / "local-backups"
    backups = list(backup_root.rglob("learning-rate.md"))
    assert backups and backups[0].read_bytes() == b"# my own annotations\n"
    # user-created files stay; clean deletions land
    assert own.read_bytes() == b"# mine\n"
    assert not (data / "knowledge" / "errors" / "common-errors.md").exists()


def test_first_update_adopts_launcher_seeded_files(channel):
    """F3-3 item 4 reconciliation: a fresh install seeds knowledge/templates/
    skills into the data root (launcher, never registered). The FIRST channel
    update must ADOPT them — identical content lands as unchanged, a seeded
    file the user already edited is backed up before the release version
    lands, the user's own notes stay, and afterwards every release path is
    tracked so later updates reach them (they no longer behave as user files).
    """
    updater = channel["updater"]
    data = channel["paths"].user_data_dir(PLUGIN_ID)
    # Simulate the launcher having just seeded the v1 bundle verbatim...
    for rel, body in V1.items():
        root = data / "pi-agent" if rel.startswith("skills/") else data
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
    # ...one seeded file was already edited by the user...
    (data / "knowledge" / "learning-rate.md").write_bytes(b"# user tweaks on day one\n")
    # ...plus a genuine own note the release does not own.
    own = data / "knowledge" / "my-own-notes.md"
    own.write_bytes(b"# mine\n")

    index, payload = release("2026.08.29-1", V1)
    publish(channel, index, payload)
    report = updater.update(PLUGIN_ID)

    assert report["backed_up"] == ["knowledge/learning-rate.md"]      # edits protected, then updated
    assert report["updated"] == ["knowledge/learning-rate.md"]
    assert sorted(report["unchanged"]) == sorted(set(V1) - {"knowledge/learning-rate.md"})
    assert not report["added"]
    assert (data / "knowledge" / "learning-rate.md").read_bytes() == V1["knowledge/learning-rate.md"]
    backups = list((data / "managed" / "local-backups").rglob("learning-rate.md"))
    assert backups and backups[0].read_bytes() == b"# user tweaks on day one\n"
    assert own.read_bytes() == b"# mine\n"                            # own file untouched
    manifest = json.loads((data / "managed" / "managed-manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["files"]) == set(V1)                          # adopted: tracked from now on
    # and a following release DOES reach the previously-seeded content:
    V2 = dict(V1, **{"knowledge/errors/common-errors.md": b"# errors v2\n"})
    index2, payload2 = release("2026.08.29-2", V2)
    publish(channel, index2, payload2)
    report2 = updater.update(PLUGIN_ID)
    assert report2["updated"] == ["knowledge/errors/common-errors.md"]


def test_repeat_update_is_unchanged(channel):
    updater = channel["updater"]
    index, payload = release("2026.08.29-1", V1)
    publish(channel, index, payload)
    updater.update(PLUGIN_ID)
    report = updater.update(PLUGIN_ID)
    assert sorted(report["unchanged"]) == sorted(V1)
    assert not report["backed_up"]


def test_tampered_index_signature_leaves_everything_whole(channel):
    updater = channel["updater"]
    index, payload = release("2026.08.29-1", V1)
    publish(channel, index, payload)
    assert updater.update(PLUGIN_ID)["assetsVersion"] == "2026.08.29-1"

    V2 = dict(V1, **{"knowledge/learning-rate.md": b"# hostile\n"})
    bad_index, bad_payload = release("2026.08.29-2", V2, key=b"attacker-key")
    publish(channel, bad_index, bad_payload)
    with pytest.raises(AssetsError) as exc:
        updater.update(PLUGIN_ID)
    assert exc.value.code == "MARKETPLACE_ASSETS_UNTRUSTED"
    data = channel["paths"].user_data_dir(PLUGIN_ID)
    assert (data / "knowledge" / "learning-rate.md").read_bytes() == b"# lr v1\n"
    manifest = json.loads((data / "managed" / "managed-manifest.json").read_text(encoding="utf-8"))
    assert manifest["assetsVersion"] == "2026.08.29-1"


def test_zip_body_not_matching_pinned_sha_is_refused(channel):
    updater = channel["updater"]
    index, payload = release("2026.08.29-1", V1)
    publish(channel, index, payload)
    updater.update(PLUGIN_ID)
    # mutate the served body in place: same size, one flipped byte.
    tampered = payload[:-1] + bytes([payload[-1] ^ 0xFF])
    channel["handler"].serving[index["file"]] = tampered
    with pytest.raises(AssetsError) as exc:
        updater.update(PLUGIN_ID)
    assert exc.value.code == "MARKETPLACE_ASSETS_CHECKSUM_MISMATCH"
    data = channel["paths"].user_data_dir(PLUGIN_ID)
    assert (data / "knowledge" / "learning-rate.md").read_bytes() == b"# lr v1\n"


def test_traversal_member_in_zip_is_refused(channel):
    updater = channel["updater"]
    evil = {"knowledge/../../escape.md": b"# escape\n"}
    index, payload = release("2026.08.29-1", evil)
    publish(channel, index, payload)
    with pytest.raises(AssetsError) as exc:
        updater.update(PLUGIN_ID)
    assert exc.value.code == "MARKETPLACE_ASSETS_PACKAGE_INVALID"
    assert not (channel["paths"].root.parent / "escape.md").exists()


def test_offline_status_and_update_report_without_breaking(tmp_path):
    trust = TrustStore({KEY_ID: (PUBLISHER, KEY)})
    updater = AssetsUpdater(MarketplacePaths(tmp_path / "offline-root"), trust)  # channel closed
    assert updater.status(PLUGIN_ID) == {"configured": False}
    with pytest.raises(AssetsError) as exc:
        updater.update(PLUGIN_ID)
    assert exc.value.code == "MARKETPLACE_ASSETS_OFFLINE"


def test_failure_mid_apply_rolls_the_tree_back(channel, monkeypatch):
    updater = channel["updater"]
    index, payload = release("2026.08.29-1", V1)
    publish(channel, index, payload)
    updater.update(PLUGIN_ID)

    V2 = dict(V1)
    V2["knowledge/learning-rate.md"] = b"# lr v2\n"
    V2["knowledge/new-one.md"] = b"# one\n"
    V2["knowledge/new-two.md"] = b"# two\n"
    index2, payload2 = release("2026.08.29-2", V2)
    publish(channel, index2, payload2)

    original_write = AssetsUpdater._atomic_write
    calls = {"n": 0}

    def flaky(target, body):
        calls["n"] += 1
        if calls["n"] == 3:
            raise OSError("simulated disk failure mid-apply")
        original_write(target, body)

    monkeypatch.setattr(AssetsUpdater, "_atomic_write", staticmethod(flaky))
    with pytest.raises(OSError):
        updater.update(PLUGIN_ID)

    data = channel["paths"].user_data_dir(PLUGIN_ID)
    assert (data / "knowledge" / "learning-rate.md").read_bytes() == b"# lr v1\n"
    assert not (data / "knowledge" / "new-one.md").exists()
    assert not (data / "knowledge" / "new-two.md").exists()
    manifest = json.loads((data / "managed" / "managed-manifest.json").read_text(encoding="utf-8"))
    assert manifest["assetsVersion"] == "2026.08.29-1"  # manifest never swapped

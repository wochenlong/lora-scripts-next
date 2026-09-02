"""Trust v2 (Ed25519) contract — closes Copilot C-2 on PR #308.

The v1 root shipped an HMAC SECRET to every client, so anyone who unpacked a
bundle could mint catalogs that every installed host would accept. The v2
root ships PUBLIC keys only and the trust root (never the artifact) decides
the verification algorithm. These tests pin:

1. canonical bytes are FROZEN (golden digests captured from the pre-v2 code
   — the same signed bytes verify under both algorithms forever);
2. Ed25519 verify on all three surfaces (entry / catalog / assets index);
3. holding the shipped trust.json grants NO signing power (the whole point);
4. algorithm substitution/downgrade through a tampered root fails closed;
5. the v1 HMAC path keeps working verbatim (2-tuple keys, v1 roots).
"""
from __future__ import annotations

import hashlib
import hmac as hmac_module
import json
from pathlib import Path

import pytest

from mikazuki.plugin_marketplace.models import MarketplaceCatalog, MarketplaceEntry
from mikazuki.plugin_marketplace.trust import (
    TrustError,
    TrustStore,
    canonical_assets_index_payload,
    canonical_catalog_payload,
    canonical_entry_payload,
    load_trust_root,
)

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

PUBLISHER = "approved-publisher-id"
ED_KEY_ID = "release-2026b"
_PRIVATE = Ed25519PrivateKey.generate()
PUBLIC_HEX = _PRIVATE.public_key().public_bytes_raw().hex()

ENTRY_DATA = {
    "id": "next-trainer-pi-agent",
    "name": "Next Trainer Pi Agent",
    "publisher_id": PUBLISHER,
    "description": "Optional agent",
    "latest_version": "0.1.0",
    "channel": "stable",
    "host_compatibility": ">=2.9.2 <3.0.0",
    "platforms": ["win32-x64"],
    "package_size": 1234,
    "permissions_summary": ["model-provider", "training-config"],
    "license": "MIT",
    "package_url": "https://market.invalid/plugins/agent.zip",
    "sha256": "a" * 64,
    "signing_key_id": "test-key",
    "published_at": "2026-08-21T00:00:00Z",
    "signature": "",
}
CATALOG_DATA = {
    "schemaVersion": 1,
    "publisherId": PUBLISHER,
    "signingKeyId": "test-key",
    "generatedAt": "2026-08-21T00:00:00Z",
    "entries": [ENTRY_DATA],
    "signature": "",
}
ASSETS_INDEX = {
    "schemaVersion": 1,
    "assetsVersion": "2026.08.30-2",
    "file": "trainer-assets-2026.08.30-2.zip",
    "url": "https://r.invalid/trainer-assets-2026.08.30-2.zip",
    "size": 42,
    "sha256": "b" * 64,
    "generatedAt": "2026-08-30T00:00:00Z",
    "publisherId": "next-trainer-project",
    "signingKeyId": "test-key",
    "signature": "c" * 64,
}

# Golden digests of the canonical payload bytes, captured from the PRE-Ed25519
# code on 2026-08-30. The signing algorithm may evolve; the BYTES NEVER MOVE.
GOLDEN_CANONICAL_SHA256 = {
    "entry": "5d61eba931b0ace24409fdafe5f3bd949b09cc3f96b9dab32226ffed7c10f536",
    "entry_packages": "55c674b4c31ceca7458620cb2109689f1388a2bb155765c4ab93f13b7fdc7807",
    "catalog": "028c5a9e6b8a33325ac9a3c082c2e3effdc574d080273b9429b21fb39ff27729",
    "assets_index": "574e00839e81c72534b4aa0e8ee6cb6b0c47c3c08abb5d537b75732d615d42fa",
}


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_canonical_payloads_are_byte_frozen():
    entry = MarketplaceEntry.model_validate(ENTRY_DATA)
    entry_packages = MarketplaceEntry.model_validate({
        **ENTRY_DATA,
        "packages": [{"platform": "win32-x64", "package_url": ENTRY_DATA["package_url"], "package_size": 1234, "sha256": "a" * 64}],
    })
    catalog = MarketplaceCatalog.model_validate(CATALOG_DATA)
    assert _digest(canonical_entry_payload(entry)) == GOLDEN_CANONICAL_SHA256["entry"]
    assert _digest(canonical_entry_payload(entry_packages)) == GOLDEN_CANONICAL_SHA256["entry_packages"]
    assert _digest(canonical_catalog_payload(catalog)) == GOLDEN_CANONICAL_SHA256["catalog"]
    assert _digest(canonical_assets_index_payload(ASSETS_INDEX)) == GOLDEN_CANONICAL_SHA256["assets_index"]


def _ed_sign(payload: bytes) -> str:
    return _PRIVATE.sign(payload).hex()


def _ed_entry(**overrides) -> MarketplaceEntry:
    data = {**ENTRY_DATA, "signing_key_id": ED_KEY_ID}
    data.update(overrides)
    entry = MarketplaceEntry.model_validate(data)
    data["signature"] = _ed_sign(canonical_entry_payload(entry))
    return MarketplaceEntry.model_validate(data)


def _ed_catalog() -> MarketplaceCatalog:
    data = {**CATALOG_DATA, "signingKeyId": ED_KEY_ID}
    catalog = MarketplaceCatalog.model_validate(data)
    data["signature"] = _ed_sign(canonical_catalog_payload(catalog))
    return MarketplaceCatalog.model_validate(data)


def _ed_index() -> dict:
    index = {**ASSETS_INDEX, "signingKeyId": ED_KEY_ID, "publisherId": PUBLISHER}
    index["signature"] = _ed_sign(canonical_assets_index_payload(index))
    return index


def _v2_root(**record_overrides) -> dict:
    record = {"publisherId": PUBLISHER, "algorithm": "ed25519", "publicKeyHex": PUBLIC_HEX}
    record.update(record_overrides)
    return {"schemaVersion": 2, "keys": {ED_KEY_ID: record}, "revokedKeys": []}


def _write_root(tmp_path: Path, payload: dict) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "trust.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_v2_root_verifies_all_three_ed25519_surfaces(tmp_path):
    root = load_trust_root(_write_root(tmp_path, _v2_root()))
    root.verify_catalog(_ed_catalog())
    root.verify_assets_index(_ed_index())

    blob = b"fake package bytes"
    package = tmp_path / "agent.zip"
    package.write_bytes(blob)
    entry = _ed_entry(package_size=len(blob), sha256=hashlib.sha256(blob).hexdigest())
    root.verify(entry, package)


def test_v2_root_rejects_tampered_payloads(tmp_path):
    root = load_trust_root(_write_root(tmp_path, _v2_root()))
    tampered_catalog = _ed_catalog().model_dump(mode="json", by_alias=True)
    tampered_catalog["publisherId"] = PUBLISHER  # publisher gate would pass; below is the signed-field tamper
    tampered_catalog["generatedAt"] = "2026-08-22T00:00:00Z"
    with pytest.raises(TrustError):
        root.verify_catalog(MarketplaceCatalog.model_validate(tampered_catalog))
    tampered_index = _ed_index()
    tampered_index["size"] = tampered_index["size"] + 1
    with pytest.raises(TrustError):
        root.verify_assets_index(tampered_index)


def test_shipped_public_key_grants_no_signing_power(tmp_path):
    """THE C-2 closure test: attacker holds the exact bytes of the shipped root."""
    root = load_trust_root(_write_root(tmp_path, _v2_root()))
    catalog = _ed_catalog()
    index = _ed_index()
    root.verify_catalog(catalog)  # control: genuine signature verifies

    public_bytes = bytes.fromhex(PUBLIC_HEX)

    # 1. HMAC "signature" using the public key as the secret (old scheme, new material).
    forged = catalog.model_dump(mode="json", by_alias=True)
    forged["signature"] = hmac_module.new(public_bytes, canonical_catalog_payload(catalog), hashlib.sha256).hexdigest()
    with pytest.raises(TrustError, match="catalog signature verification failed"):
        root.verify_catalog(MarketplaceCatalog.model_validate(forged))

    # 2. Same trick on the assets envelope.
    forged_index = dict(index)
    forged_index["signature"] = hmac_module.new(public_bytes, canonical_assets_index_payload(index), hashlib.sha256).hexdigest()
    with pytest.raises(TrustError, match="assets index signature verification failed"):
        root.verify_assets_index(forged_index)

    # 3. Re-interpret the shipped public key as an HMAC trust root: the
    #    attacker's v1-style forged catalog fails against it too (wrong scheme
    #    and wrong shape — the hmac branch only accepts 64-hex signatures).
    hmac_style = TrustStore({ED_KEY_ID: (PUBLISHER, public_bytes)})
    with pytest.raises(TrustError):
        hmac_style.verify_catalog(catalog)

    # 4. Truncating the Ed25519 signature to HMAC width is still not a signature.
    short = catalog.model_dump(mode="json", by_alias=True)
    short["signature"] = catalog.signature[:64]
    with pytest.raises(TrustError):
        root.verify_catalog(MarketplaceCatalog.model_validate(short))


def test_trust_root_alone_decides_the_algorithm(tmp_path):
    catalog = _ed_catalog()
    # A root that (wrongly) labels this key hmac-sha256 cannot be talked into
    # accepting the ed25519 signature: 128-hex fails the HMAC shape gate.
    downgraded = _write_root(tmp_path / "down", {"schemaVersion": 2, "keys": {ED_KEY_ID: {"publisherId": PUBLISHER, "keyHex": PUBLIC_HEX + PUBLIC_HEX}}, "revokedKeys": []})
    with pytest.raises(TrustError):
        load_trust_root(downgraded).verify_catalog(catalog)


def test_v2_root_shape_is_strict(tmp_path):
    bad_records = {
        "ed25519 carrying keyHex": {"algorithm": "ed25519", "publicKeyHex": PUBLIC_HEX, "keyHex": PUBLIC_HEX * 2},
        "ed25519 without publicKeyHex": {"algorithm": "ed25519"},
        "ed25519 short public key": {"algorithm": "ed25519", "publicKeyHex": PUBLIC_HEX[:62]},
        "unknown algorithm": {"algorithm": "rsa-4096", "publicKeyHex": PUBLIC_HEX},
    }
    for label, override in bad_records.items():
        record = {"publisherId": PUBLISHER}
        record.update(override)
        root = _write_root(tmp_path, {"schemaVersion": 2, "keys": {ED_KEY_ID: record}, "revokedKeys": []})
        with pytest.raises(TrustError):
            load_trust_root(root)


def test_v2_root_honors_revocation_and_unknown_keys(tmp_path):
    payload = _v2_root()
    payload["revokedKeys"] = [ED_KEY_ID]
    root = load_trust_root(_write_root(tmp_path, payload))
    with pytest.raises(TrustError, match="revoked catalog signing key"):
        root.verify_catalog(_ed_catalog())
    with pytest.raises(TrustError, match="unknown assets signing key"):
        root.verify_assets_index(_ed_index() | {"signingKeyId": "other-key"})


def test_v1_hmac_path_is_unchanged(tmp_path):
    key = b"stage-1-mock-signing-key"
    data = {**CATALOG_DATA}
    catalog = MarketplaceCatalog.model_validate(data)
    data["signature"] = hmac_module.new(key, canonical_catalog_payload(catalog), hashlib.sha256).hexdigest()
    catalog = MarketplaceCatalog.model_validate(data)
    root = load_trust_root(_write_root(tmp_path, {"keys": {"test-key": {"publisherId": PUBLISHER, "keyHex": key.hex()}}, "revokedKeys": []}))
    root.verify_catalog(catalog)
    # Two-tuple construction (the 25 existing call sites) keeps HMAC semantics.
    TrustStore({"test-key": (PUBLISHER, key)}).verify_catalog(catalog)

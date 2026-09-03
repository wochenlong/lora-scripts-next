"""P1-5 trust update channel: rotation/revocation without a host re-release.

trust-update.json (governed release artifact) carries a NEW trust root
signed by a key the CURRENT trust already trusts, with a strictly
advancing seq. The host applies it at startup / catalog refresh, persists
the applied root (restart-proof), and is never bricked: ANY verification
failure keeps the current trust in force.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest

from mikazuki.plugin_marketplace.trust import (
    TrustError,
    TrustStore,
    _parse_trust_root_payload,
    build_trust_update,
    canonical_trust_update_payload,
    load_applied_trust,
    trust_root_object,
    trust_root_payload,
    verify_trust_update,
    write_applied_trust,
)

PUBLISHER = "next-trainer-project"


def _key_hex(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def _root(key_records: dict[str, dict], revoked: list[str] | None = None) -> dict:
    return {"keys": key_records, "revokedKeys": revoked or []}


def _hmac_key(key_id: str, tag: str) -> dict:
    return {key_id: {"publisherId": PUBLISHER, "keyHex": _key_hex(tag)}}


def _sign(store: TrustStore, key_id: str, update: dict) -> None:
    """Sign a trust-update dict with the HMAC key `key_id` from `store`."""
    material = store._keys[key_id][1]
    sig = hmac.new(material, canonical_trust_update_payload(update), hashlib.sha256).hexdigest()
    update["signature"] = sig


def test_two_hop_rotation_chain_bundled_to_a_to_b():
    """Bundled root (X) -> update 1 signed by X (adds A) -> update 2 signed
    by A (adds B, revokes X and A). Every hop verifies; the final trust
    only accepts B."""
    x = _hmac_key("x", "key-x")
    a = _hmac_key("a", "key-a")
    b = _hmac_key("b", "key-b")

    store0 = _parse_trust_root_payload(_root(x))
    # Hop 1: X signs a root that trusts X+A.
    update1 = {"seq": 1, "trust": _root({**x, **a}), "signingKeyId": "x"}
    _sign(store0, "x", update1)
    store1, seq1 = verify_trust_update(store0, 0, json.dumps(update1).encode())
    assert seq1 == 1
    assert set(store1._keys) == {"x", "a"}

    # Hop 2: A signs a root that trusts only B and revokes X and A.
    update2 = {"seq": 2, "trust": _root(b, revoked=["x", "a"]), "signingKeyId": "a"}
    _sign(store1, "a", update2)
    store2, seq2 = verify_trust_update(store1, seq1, json.dumps(update2).encode())
    assert seq2 == 2
    assert set(store2._keys) == {"b"}
    assert store2.revoked_key_ids == ["a", "x"]

    # The fingerprint moved with the rotation.
    assert trust_root_payload(store0) != trust_root_payload(store2)


def test_revoked_signer_is_rejected():
    x = _hmac_key("x", "key-x")
    a = _hmac_key("a", "key-a")
    store0 = _parse_trust_root_payload(_root(x))
    update = {"seq": 1, "trust": _root(a), "signingKeyId": "x"}
    _sign(store0, "x", update)
    # Now x is revoked in the effective trust: its signature no longer counts.
    store_x_revoked = _parse_trust_root_payload(_root({**x, **a}, revoked=["x"]))
    with pytest.raises(TrustError, match="revoked key"):
        verify_trust_update(store_x_revoked, 0, json.dumps(update).encode())


def test_seq_rollback_and_replay_rejected():
    x = _hmac_key("x", "key-x")
    a = _hmac_key("a", "key-a")
    store0 = _parse_trust_root_payload(_root(x))
    update = {"seq": 5, "trust": _root({**x, **a}), "signingKeyId": "x"}
    _sign(store0, "x", update)
    payload = json.dumps(update).encode()
    store1, _ = verify_trust_update(store0, 0, payload)
    # Replay of the same update (seq 5 <= 5) must be rejected.
    with pytest.raises(TrustError, match="does not advance"):
        verify_trust_update(store1, 5, payload)
    # An older seq (3) is a downgrade attack: rejected.
    old = {"seq": 3, "trust": _root(a), "signingKeyId": "x"}
    _sign(store1, "x", old)
    with pytest.raises(TrustError, match="does not advance"):
        verify_trust_update(store1, 5, json.dumps(old).encode())


def test_bad_signature_is_rejected():
    x = _hmac_key("x", "key-x")
    a = _hmac_key("a", "key-a")
    store0 = _parse_trust_root_payload(_root(x))
    update = {"seq": 1, "trust": _root({**x, **a}), "signingKeyId": "x"}
    _sign(store0, "x", update)
    update["signature"] = "00" * 32  # corrupted
    with pytest.raises(TrustError, match="signature verification failed"):
        verify_trust_update(store0, 0, json.dumps(update).encode())


def test_unknown_signer_is_rejected():
    x = _hmac_key("x", "key-x")
    a = _hmac_key("a", "key-a")
    store0 = _parse_trust_root_payload(_root(x))
    # Forged: signed by a key the host does not trust at all.
    rogue = TrustStore({"rogue": (PUBLISHER, bytes.fromhex(_key_hex("rogue")), "hmac-sha256")})
    update = {"seq": 1, "trust": _root({**x, **a}), "signingKeyId": "rogue"}
    _sign(rogue, "rogue", update)
    with pytest.raises(TrustError, match="unknown key"):
        verify_trust_update(store0, 0, json.dumps(update).encode())


def test_malformed_payloads_are_rejected():
    x = _hmac_key("x", "key-x")
    store0 = _parse_trust_root_payload(_root(x))
    with pytest.raises(TrustError):
        verify_trust_update(store0, 0, b"not json at all")
    with pytest.raises(TrustError):
        verify_trust_update(store0, 0, json.dumps([1, 2, 3]).encode())
    with pytest.raises(TrustError):
        verify_trust_update(store0, 0, json.dumps({"seq": "1", "trust": _root(x)}).encode())
    with pytest.raises(TrustError):
        verify_trust_update(store0, 0, json.dumps({"seq": 0, "trust": _root(x), "signingKeyId": "x"}).encode())
    with pytest.raises(TrustError):
        verify_trust_update(store0, 0, json.dumps({"seq": 1, "trust": "nope", "signingKeyId": "x"}).encode())


def test_update_introducing_a_self_signed_key_fails_chain():
    """An update cannot trust its own new key to sign itself: the signer
    must exist in the CURRENT trust, not just in the proposed root."""
    x = _hmac_key("x", "key-x")
    a = _hmac_key("a", "key-a")
    store0 = _parse_trust_root_payload(_root(x))
    update = {"seq": 1, "trust": _root(a), "signingKeyId": "a"}  # a not in current trust
    _sign(TrustStore({"a": (PUBLISHER, bytes.fromhex(_key_hex("key-a")), "hmac-sha256")}), "a", update)
    with pytest.raises(TrustError, match="unknown key"):
        verify_trust_update(store0, 0, json.dumps(update).encode())


def test_applied_trust_roundtrip_persists(tmp_path: Path):
    x = _hmac_key("x", "key-x")
    a = _hmac_key("a", "key-a")
    store0 = _parse_trust_root_payload(_root(x))
    update = {"seq": 7, "trust": _root({**x, **a}), "signingKeyId": "x"}
    _sign(store0, "x", update)
    store1, seq = verify_trust_update(store0, 0, json.dumps(update).encode())

    applied_file = tmp_path / "trust-applied.json"
    write_applied_trust(applied_file, store1, seq, source={"signingKeyId": "x", "origin": "test"})
    loaded, loaded_seq = load_applied_trust(applied_file)
    assert loaded_seq == 7
    assert loaded.fingerprint() == store1.fingerprint()
    assert loaded.key_ids == ["a", "x"]
    # The re-materialized root object is byte-stable.
    assert trust_root_object(store1) == trust_root_object(loaded)


def test_corrupted_applied_trust_raises(tmp_path: Path):
    applied_file = tmp_path / "trust-applied.json"
    applied_file.write_text("{broken", encoding="utf-8")
    with pytest.raises(TrustError):
        load_applied_trust(applied_file)
    # A valid file with the wrong schema is rejected too.
    applied_file.write_text(json.dumps({"seq": 1, "trust": {"keys": {}}}), encoding="utf-8")
    with pytest.raises(TrustError):
        load_applied_trust(applied_file)


def test_fingerprint_is_stable_and_changes_with_root():
    x = _hmac_key("x", "key-x")
    a = _hmac_key("a", "key-a")
    store0 = _parse_trust_root_payload(_root(x))
    fp0 = store0.fingerprint()
    assert len(fp0) == 64 and all(c in "0123456789abcdef" for c in fp0)
    assert store0.fingerprint() == fp0  # stable
    store1 = _parse_trust_root_payload(_root({**x, **a}))
    assert store1.fingerprint() != fp0  # rotates with the root
    # The fingerprint must not embed key material verbatim.
    assert _key_hex("key-x") not in fp0


def test_build_trust_update_validates():
    x = _hmac_key("x", "key-x")
    a = _hmac_key("a", "key-a")
    root = _root({**x, **a})
    artifact = build_trust_update(root, 1, "x", "ab" * 32)
    payload = json.loads(artifact)
    assert payload["seq"] == 1
    assert payload["signingKeyId"] == "x"
    assert payload["trust"] == root
    with pytest.raises(TrustError):
        build_trust_update(root, 0, "x", "ab" * 32)
    with pytest.raises(TrustError):
        build_trust_update({"nope": 1}, 1, "x", "ab" * 32)  # malformed root
    with pytest.raises(TrustError):
        build_trust_update(root, 1, "", "ab" * 32)


def test_apply_pending_trust_update_host_flow(tmp_path, monkeypatch):
    """Host flow: trust-update.json in the marketplace root is verified
    against the effective trust, persisted, archived, and the live
    manager/catalog references are swapped. Rejected updates leave the
    trust untouched and the file in place for audit/retry."""
    import types

    from mikazuki.plugin_marketplace import api as api_module

    shipped = _parse_trust_root_payload(_root(_hmac_key("shipped", "shipped-key")))
    rotated_root = _root(_hmac_key("rotated", "rotated-key"), revoked=["shipped"])
    update = {"seq": 1, "trust": rotated_root, "signingKeyId": "shipped"}
    _sign(shipped, "shipped", update)

    monkeypatch.setattr(api_module, "_trust", shipped)
    monkeypatch.setattr(api_module, "_trust_seq", 0)
    monkeypatch.setattr(
        api_module,
        "_manager",
        types.SimpleNamespace(paths=types.SimpleNamespace(root=tmp_path), trust=shipped),
    )
    monkeypatch.setattr(api_module, "_catalog", types.SimpleNamespace(trust=shipped))

    assert api_module._apply_pending_trust_update() is False  # no update file yet
    (tmp_path / "trust-update.json").write_bytes(json.dumps(update).encode())
    assert api_module._apply_pending_trust_update() is True
    assert api_module._trust_seq == 1
    assert api_module._trust.fingerprint() == _parse_trust_root_payload(rotated_root).fingerprint()
    # Persisted (restart-proof) + archived (audit) + original consumed.
    assert (tmp_path / "trust-applied.json").is_file()
    assert (tmp_path / "trust-update.json.applied.1").is_file()
    assert not (tmp_path / "trust-update.json").is_file()
    # Live references swapped — subsequent verification uses the new trust.
    assert api_module._manager.trust is api_module._trust
    assert api_module._catalog.trust is api_module._trust
    # Nothing left to do.
    assert api_module._apply_pending_trust_update() is False

    # A forged update: rejected, trust untouched, file kept for audit.
    bad = {"seq": 2, "trust": rotated_root, "signingKeyId": "shipped"}
    bad["signature"] = "00" * 32
    (tmp_path / "trust-update.json").write_bytes(json.dumps(bad).encode())
    fingerprint_before = api_module._trust.fingerprint()
    assert api_module._apply_pending_trust_update() is False
    assert api_module._trust.fingerprint() == fingerprint_before
    assert (tmp_path / "trust-update.json").is_file()


def test_wiring_prefers_applied_trust_over_shipped(tmp_path, monkeypatch):
    """Host assembly: a valid applied root wins over the shipped trust.json;
    a corrupted applied file falls back (never bricked)."""
    from mikazuki.plugin_marketplace.api import _local_catalog_wiring, _marketplace_paths

    bundled = tmp_path / "plugin-marketplace"
    (bundled / "packages").mkdir(parents=True)
    (bundled / "trust.json").write_text(
        json.dumps(_root(_hmac_key("shipped", "shipped-key")), ensure_ascii=False), encoding="utf-8"
    )
    (bundled / "catalog.json").write_text("{}", encoding="utf-8")
    for var in ("MIKAZUKI_MARKETPLACE_CATALOG", "MIKAZUKI_MARKETPLACE_TRUST",
                "MIKAZUKI_MARKETPLACE_CATALOG_URL", "MIKAZUKI_MARKETPLACE_PACKAGE_ROOT",
                "MIKAZUKI_MARKETPLACE_PACKAGE_MIRROR", "MIKAZUKI_PLUGIN_MARKETPLACE_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MIKAZUKI_PLUGIN_MARKETPLACE_ROOT", str(tmp_path / "mroot"))
    (tmp_path / "mroot").mkdir()

    # No applied file yet: the shipped root is active (seq 0).
    trust, seq, source, _acquirer = _local_catalog_wiring(_marketplace_paths())
    assert seq == 0 and "shipped" in trust.key_ids

    # An applied root (signed chain verified elsewhere) takes precedence.
    applied_store = _parse_trust_root_payload(_root(_hmac_key("rotated", "rotated-key")))
    write_applied_trust(
        (tmp_path / "mroot") / "trust-applied.json",
        applied_store,
        3,
        source={"signingKeyId": "shipped", "origin": "test"},
    )
    trust2, seq2, _source2, _acquirer2 = _local_catalog_wiring(_marketplace_paths())
    assert seq2 == 3
    assert "rotated" in trust2.key_ids and "shipped" not in trust2.key_ids

    # Corrupted applied file: fall back to the shipped root, never brick.
    (tmp_path / "mroot" / "trust-applied.json").write_text("{corrupt", encoding="utf-8")
    trust3, seq3, _source3, _acquirer3 = _local_catalog_wiring(_marketplace_paths())
    assert seq3 == 0 and "shipped" in trust3.key_ids

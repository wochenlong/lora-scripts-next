from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .models import MarketplaceCatalog, MarketplaceEntry


logger = logging.getLogger("mikazuki.plugin_marketplace.trust")


class TrustError(ValueError):
    pass


def load_trust_root(path: Path) -> TrustStore:
    """Load a host-supplied trust root file.

    v1 shape:  {"keys": {"<id>": {"publisherId": str, "keyHex": str}},
                "revokedKeys": [str, ...]}
    v2 shape:  {"keys": {"<id>": {"publisherId": str, "algorithm": "ed25519",
                                  "publicKeyHex": <64 hex>}},
                "revokedKeys": [str, ...]}

    The ALGORITHM IS PART OF THE TRUST ROOT, never of the signed artifact:
    an artifact can never negotiate which algorithm verifies it (downgrade
    and substitution attacks are structurally impossible). A v2 root ships
    public keys only — extracting a shipped trust.json grants verification,
    never signing power.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TrustError(f"trust root is unreadable: {path}") from exc
    return _parse_trust_root_payload(payload)


def _parse_trust_root_payload(payload: dict) -> TrustStore:
    """Build the verifier from a trust-root JSON object (shape contract
    documented on load_trust_root)."""
    if not isinstance(payload, dict):
        raise TrustError("trust root must be a JSON object")
    keys_block = payload.get("keys")
    revoked_block = payload.get("revokedKeys") or []
    if not isinstance(keys_block, dict) or not isinstance(revoked_block, list):
        raise TrustError("trust root shape is invalid")
    keys: dict[str, tuple[str, bytes, str]] = {}
    for key_id, record in keys_block.items():
        if not isinstance(record, dict):
            raise TrustError(f"trust key entry is invalid: {key_id}")
        publisher = record.get("publisherId")
        if not isinstance(publisher, str) or not publisher:
            raise TrustError(f"trust key publisher is invalid: {key_id}")
        algorithm = record.get("algorithm") or "hmac-sha256"
        if not isinstance(algorithm, str):
            raise TrustError(f"trust key algorithm is invalid: {key_id}")
        if algorithm == "ed25519":
            if "keyHex" in record:
                raise TrustError(f"ed25519 trust key must not carry keyHex: {key_id}")
            public_hex = record.get("publicKeyHex")
            if not isinstance(public_hex, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", public_hex):
                raise TrustError(f"ed25519 public key must be exactly 64 hexadecimal characters: {key_id}")
            keys[str(key_id)] = (publisher, bytes.fromhex(public_hex), "ed25519")
        elif algorithm == "hmac-sha256":
            key_hex = record.get("keyHex")
            if not isinstance(key_hex, str) or not re.fullmatch(r"[0-9a-fA-F]+", key_hex) or len(key_hex) < 32:
                raise TrustError(f"trust key material is invalid: {key_id}")
            keys[str(key_id)] = (publisher, bytes.fromhex(key_hex), "hmac-sha256")
        else:
            raise TrustError(f"unknown trust key algorithm: {key_id}: {algorithm}")
    revoked = {item for item in revoked_block if isinstance(item, str)}
    return TrustStore(keys, revoked_keys=revoked)


def canonical_entry_payload(entry: MarketplaceEntry) -> bytes:
    value = entry.model_dump(mode="json", exclude={"signature"}, by_alias=True)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def canonical_catalog_payload(catalog: MarketplaceCatalog) -> bytes:
    value = catalog.model_dump(mode="json", exclude={"signature"}, by_alias=True)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _version_tuple(version: str) -> tuple[int, ...]:
    match = re.match(r"^(\d+(?:\.\d+)*)", version.strip())
    if not match:
        raise TrustError(f"invalid version: {version}")
    return tuple(int(part) for part in match.group(1).split("."))


def version_satisfies(version: str, expression: str) -> bool:
    actual = _version_tuple(version)
    clauses = [part for part in expression.replace(",", " ").split() if part]
    if not clauses:
        return False
    for clause in clauses:
        match = re.fullmatch(r"(>=|<=|==|>|<)(\d+(?:\.\d+)*)", clause)
        if not match:
            raise TrustError(f"unsupported host compatibility expression: {expression}")
        expected = _version_tuple(match.group(2))
        width = max(len(actual), len(expected))
        left = actual + (0,) * (width - len(actual))
        right = expected + (0,) * (width - len(expected))
        operator = match.group(1)
        if operator == ">=" and not left >= right:
            return False
        if operator == "<=" and not left <= right:
            return False
        if operator == ">" and not left > right:
            return False
        if operator == "<" and not left < right:
            return False
        if operator == "==" and not left == right:
            return False
    return True


def canonical_assets_index_payload(index: dict) -> bytes:
    """Canonical bytes for a managed-assets index envelope.

    Mirrors canonical_catalog_payload: the signed fields are a fixed set, the
    signature itself is excluded, and the same HMAC keys from trust.json sign
    it. Field set is pinned here so publisher and verifier can never disagree.
    """
    signed_fields = (
        "schemaVersion",
        "assetsVersion",
        "file",
        "url",
        "size",
        "sha256",
        "generatedAt",
        "publisherId",
        "signingKeyId",
    )
    body = {key: index.get(key) for key in signed_fields}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _ed25519_public_key(material: bytes):
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:  # pragma: no cover - shipped via requirements.txt
        raise TrustError("ed25519 verification requires the cryptography package") from exc
    return Ed25519PublicKey.from_public_bytes(material)


class TrustStore:
    """Signature verifier dispatching on the ALGORITHM STORED IN THE TRUST ROOT.

    v1 HMAC keys keep the historical Stage-1 behavior (deterministic test
    signatures); v2 Ed25519 keys ship public material only, so a client can
    verify without ever holding signing power.
    """

    def __init__(
        self,
        keys: dict[str, tuple[str, bytes] | tuple[str, bytes, str]],
        *,
        revoked_keys: set[str] | None = None,
    ):
        # Two-tuples are HMAC keys (legacy call sites keep working verbatim);
        # three-tuples carry an explicit algorithm from the trust root.
        self._keys: dict[str, tuple[str, bytes, str]] = {
            key_id: (identity[0], identity[1], identity[2] if len(identity) > 2 else "hmac-sha256")
            for key_id, identity in keys.items()
        }
        self._revoked = set(revoked_keys or ())

    def _signature_matches(self, identity: tuple[str, bytes, str], signature: str, payload: bytes) -> bool:
        _, material, algorithm = identity
        signature = signature.strip().lower()
        if algorithm == "ed25519":
            if not re.fullmatch(r"[0-9a-f]{128}", signature):
                return False
            try:
                _ed25519_public_key(material).verify(bytes.fromhex(signature), payload)
                return True
            except TrustError:
                raise
            except Exception:
                return False
        if algorithm == "hmac-sha256":
            if not re.fullmatch(r"[0-9a-f]{64}", signature):
                return False
            expected = hmac.new(material, payload, hashlib.sha256).hexdigest()
            return hmac.compare_digest(expected, signature)
        return False  # unknown algorithm in a hand-built store: fail closed

    def verify(
        self,
        entry: MarketplaceEntry,
        package_path: Path,
        *,
        package_size: int | None = None,
        sha256: str | None = None,
    ) -> None:
        # Per-platform entries pass the resolved binding; omitted values fall
        # back to the flat (legacy) entry fields.
        expected_size = entry.package_size if package_size is None else package_size
        expected_sha = entry.sha256 if sha256 is None else sha256
        if entry.signing_key_id in self._revoked:
            raise TrustError(f"revoked signing key: {entry.signing_key_id}")
        identity = self._keys.get(entry.signing_key_id)
        if identity is None:
            raise TrustError(f"unknown signing key: {entry.signing_key_id}")
        publisher, _material, _algorithm = identity
        if publisher != entry.publisher_id:
            raise TrustError("signing key publisher does not match catalog entry")
        if not package_path.is_file():
            raise TrustError(f"package is missing: {package_path}")
        if package_path.stat().st_size != expected_size:
            raise TrustError("package size does not match catalog entry")
        digest = _sha256_file(package_path)
        if not hmac.compare_digest(digest.lower(), expected_sha.lower()):
            raise TrustError("package sha256 does not match catalog entry")
        if not self._signature_matches(identity, entry.signature, canonical_entry_payload(entry)):
            raise TrustError("catalog signature verification failed")

    def verify_catalog(self, catalog: MarketplaceCatalog) -> None:
        if catalog.signing_key_id in self._revoked:
            raise TrustError(f"revoked catalog signing key: {catalog.signing_key_id}")
        identity = self._keys.get(catalog.signing_key_id)
        if identity is None:
            raise TrustError(f"unknown catalog signing key: {catalog.signing_key_id}")
        publisher, _material, _algorithm = identity
        if publisher != catalog.publisher_id:
            raise TrustError("catalog signing key publisher does not match catalog")
        if not self._signature_matches(identity, catalog.signature, canonical_catalog_payload(catalog)):
            raise TrustError("catalog signature verification failed")

    def verify_assets_index(self, index: dict) -> None:
        """Verify a managed-assets index envelope with the same key material.

        Deliberately not a separate trust root: assets ship from the same
        governed publisher as the plugin catalog, so one key/revocation story
        covers both channels.
        """
        key_id = str(index.get("signingKeyId") or "")
        if key_id in self._revoked:
            raise TrustError(f"revoked assets signing key: {key_id}")
        identity = self._keys.get(key_id)
        if identity is None:
            raise TrustError(f"unknown assets signing key: {key_id}")
        publisher, _material, _algorithm = identity
        if publisher != index.get("publisherId"):
            raise TrustError("assets signing key publisher does not match index")
        signature = str(index.get("signature") or "")
        if not self._signature_matches(identity, signature, canonical_assets_index_payload(index)):
            raise TrustError("assets index signature verification failed")

    @staticmethod
    def verify_compatibility(entry: MarketplaceEntry, *, host_version: str, platform: str) -> None:
        if not version_satisfies(host_version, entry.host_compatibility):
            raise TrustError(f"host compatibility failed: {entry.host_compatibility}")
        if platform not in entry.platforms:
            raise TrustError(f"platform is not supported: {platform}")
        if entry.packages and all(package.platform != platform for package in entry.packages):
            raise TrustError(f"no package published for platform: {platform}")

    @property
    def key_ids(self) -> list[str]:
        return sorted(self._keys)

    @property
    def revoked_key_ids(self) -> list[str]:
        return sorted(self._revoked)

    def fingerprint(self) -> str:
        """Stable sha256 fingerprint of the effective trust root.

        UI-facing (status display): it is a one-way digest of the canonical
        root, so it identifies the effective trust without exposing key
        material (v1 HMAC roots carry secret bytes).
        """
        return hashlib.sha256(trust_root_payload(self)).hexdigest()


def trust_root_payload(store: TrustStore) -> bytes:
    """Canonical bytes of a trust root (sorted, compact) — the fingerprint
    input. HMAC material is included by design (the digest is one-way)."""
    keys = {}
    for key_id, (publisher, material, algorithm) in sorted(store._keys.items()):
        if algorithm == "ed25519":
            keys[key_id] = {"publisherId": publisher, "algorithm": "ed25519", "publicKeyHex": material.hex()}
        else:
            keys[key_id] = {"publisherId": publisher, "algorithm": "hmac-sha256", "keyHex": material.hex()}
    body = {"keys": keys, "revokedKeys": sorted(store._revoked)}
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


# ---------------------------------------------------------------------------
# P1-5: trust update channel (rotation/revocation without a host re-release)
# ---------------------------------------------------------------------------
#
# trust-update.json (shipped by a governed release, e.g. in the assets
# release):  {"seq": int, "trust": <trust root object>,
#              "signingKeyId": str, "signature": str}
# The signature is made over canonical_trust_update_payload (seq + trust +
# signingKeyId) with a key that is already TRUSTED by the host — the chain
# of trust never skips a link. The host applies the update only when the
# signature verifies AND seq strictly advances past the applied seq; every
# other outcome keeps the current trust (the host is never bricked).


def canonical_trust_update_payload(update: dict) -> bytes:
    """The signed fields of a trust update (the signature itself excluded)."""
    signed_fields = ("seq", "trust", "signingKeyId")
    body = {key: update.get(key) for key in signed_fields}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def build_trust_update(new_root: dict, seq: int, signing_key_id: str, signature: str) -> bytes:
    """Release-side builder for the trust-update artifact (pure function).

    ``signature`` is computed by the caller (the release pipeline holds the
    private key material); it must cover canonical_trust_update_payload of
    the resulting object.
    """
    _parse_trust_root_payload(new_root)  # fail closed on a malformed root
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
        raise TrustError("trust update seq must be a positive integer")
    if not isinstance(signing_key_id, str) or not signing_key_id:
        raise TrustError("trust update signingKeyId is invalid")
    if not isinstance(signature, str) or not signature:
        raise TrustError("trust update signature is invalid")
    update = {"seq": seq, "trust": new_root, "signingKeyId": signing_key_id, "signature": signature}
    return json.dumps(update, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def verify_trust_update(current: TrustStore, current_seq: int, payload: bytes) -> tuple[TrustStore, int]:
    """Verify a trust update against the CURRENT effective trust.

    Returns the (candidate store, new seq) on success and raises TrustError
    on ANY violation (malformed JSON, bad shape, unknown/revoked signing
    key, signature mismatch, non-advancing seq). Callers must keep the
    current trust on TrustError — a bad update must never brick the host.
    """
    try:
        update = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrustError("trust update is not valid JSON") from exc
    if not isinstance(update, dict):
        raise TrustError("trust update must be a JSON object")
    seq = update.get("seq")
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
        raise TrustError("trust update seq is invalid")
    if seq <= current_seq:
        raise TrustError(
            f"trust update seq {seq} does not advance past the applied seq {current_seq} (downgrade/rollback rejected)"
        )
    if not isinstance(update.get("trust"), dict):
        raise TrustError("trust update trust block is invalid")
    candidate = _parse_trust_root_payload(update["trust"])  # raises on bad key shapes
    key_id = str(update.get("signingKeyId") or "")
    if key_id in current._revoked:
        raise TrustError(f"trust update signed with revoked key: {key_id}")
    identity = current._keys.get(key_id)
    if identity is None:
        raise TrustError(f"trust update signed with unknown key: {key_id}")
    if not current._signature_matches(identity, str(update.get("signature") or ""), canonical_trust_update_payload(update)):
        raise TrustError("trust update signature verification failed")
    return candidate, seq


_APPLIED_TRUST_FILE = "trust-applied.json"


def write_applied_trust(path: Path, store: TrustStore, seq: int, *, source: dict) -> None:
    """Persist the applied trust root (atomic) so it survives restarts."""
    payload = {
        "schemaVersion": 1,
        "seq": seq,
        "trust": trust_root_object(store),
        "appliedAt": datetime.now(timezone.utc).isoformat(),
        "source": source,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def trust_root_object(store: TrustStore) -> dict:
    """Re-materialize the trust root OBJECT (file shape) from a store."""
    keys = {}
    for key_id in sorted(store._keys):
        publisher, material, algorithm = store._keys[key_id]
        if algorithm == "ed25519":
            keys[key_id] = {"publisherId": publisher, "algorithm": "ed25519", "publicKeyHex": material.hex()}
        else:
            keys[key_id] = {"publisherId": publisher, "algorithm": "hmac-sha256", "keyHex": material.hex()}
    return {"keys": keys, "revokedKeys": sorted(store._revoked)}


def load_applied_trust(path: Path) -> tuple[TrustStore, int]:
    """Load a previously applied trust root; TrustError on any corruption."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TrustError(f"applied trust root is unreadable: {path}") from exc
    if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
        raise TrustError("applied trust root schema is invalid")
    seq = payload.get("seq")
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
        raise TrustError("applied trust root seq is invalid")
    store = _parse_trust_root_payload(payload.get("trust"))
    return store, seq

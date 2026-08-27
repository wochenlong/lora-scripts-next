from __future__ import annotations

import hashlib
import hmac
import json
import re
from pathlib import Path

from .models import MarketplaceCatalog, MarketplaceEntry


class TrustError(ValueError):
    pass


def load_trust_root(path: Path) -> TrustStore:
    """Load a host-supplied trust root file (development/local catalogs).

    Shape: {"keys": {"<id>": {"publisherId": str, "keyHex": str}},
            "revokedKeys": [str, ...]}
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TrustError(f"trust root is unreadable: {path}") from exc
    if not isinstance(payload, dict):
        raise TrustError("trust root must be a JSON object")
    keys_block = payload.get("keys")
    revoked_block = payload.get("revokedKeys") or []
    if not isinstance(keys_block, dict) or not isinstance(revoked_block, list):
        raise TrustError("trust root shape is invalid")
    keys: dict[str, tuple[str, bytes]] = {}
    for key_id, record in keys_block.items():
        if not isinstance(record, dict):
            raise TrustError(f"trust key entry is invalid: {key_id}")
        publisher = record.get("publisherId")
        key_hex = record.get("keyHex")
        if not isinstance(publisher, str) or not publisher:
            raise TrustError(f"trust key publisher is invalid: {key_id}")
        if not isinstance(key_hex, str) or not re.fullmatch(r"[0-9a-fA-F]+", key_hex) or len(key_hex) < 32:
            raise TrustError(f"trust key material is invalid: {key_id}")
        keys[str(key_id)] = (publisher, bytes.fromhex(key_hex))
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


class TrustStore:
    """Stage 1 trust root using deterministic HMAC test signatures.

    Production signing keys and catalog publication remain release-governed.
    This scheme exists so every trust/hash/revocation gate is executable before
    production key material is authorized.
    """

    def __init__(
        self,
        keys: dict[str, tuple[str, bytes]],
        *,
        revoked_keys: set[str] | None = None,
    ):
        self._keys = dict(keys)
        self._revoked = set(revoked_keys or ())

    def verify(self, entry: MarketplaceEntry, package_path: Path) -> None:
        if entry.signing_key_id in self._revoked:
            raise TrustError(f"revoked signing key: {entry.signing_key_id}")
        identity = self._keys.get(entry.signing_key_id)
        if identity is None:
            raise TrustError(f"unknown signing key: {entry.signing_key_id}")
        publisher, key = identity
        if publisher != entry.publisher_id:
            raise TrustError("signing key publisher does not match catalog entry")
        if not package_path.is_file():
            raise TrustError(f"package is missing: {package_path}")
        if package_path.stat().st_size != entry.package_size:
            raise TrustError("package size does not match catalog entry")
        digest = _sha256_file(package_path)
        if not hmac.compare_digest(digest.lower(), entry.sha256.lower()):
            raise TrustError("package sha256 does not match catalog entry")
        expected = hmac.new(key, canonical_entry_payload(entry), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected.lower(), entry.signature.lower()):
            raise TrustError("catalog signature verification failed")

    def verify_catalog(self, catalog: MarketplaceCatalog) -> None:
        if catalog.signing_key_id in self._revoked:
            raise TrustError(f"revoked catalog signing key: {catalog.signing_key_id}")
        identity = self._keys.get(catalog.signing_key_id)
        if identity is None:
            raise TrustError(f"unknown catalog signing key: {catalog.signing_key_id}")
        publisher, key = identity
        if publisher != catalog.publisher_id:
            raise TrustError("catalog signing key publisher does not match catalog")
        expected = hmac.new(key, canonical_catalog_payload(catalog), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected.lower(), catalog.signature.lower()):
            raise TrustError("catalog signature verification failed")

    @staticmethod
    def verify_compatibility(entry: MarketplaceEntry, *, host_version: str, platform: str) -> None:
        if not version_satisfies(host_version, entry.host_compatibility):
            raise TrustError(f"host compatibility failed: {entry.host_compatibility}")
        if platform not in entry.platforms:
            raise TrustError(f"platform is not supported: {platform}")

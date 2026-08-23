from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    import toml
except ModuleNotFoundError:  # pragma: no cover
    import tomllib

    class _Toml:
        @staticmethod
        def loads(value: str):
            return tomllib.loads(value)

        @staticmethod
        def dumps(value: dict):
            from mikazuki.anima_fast_backend.adapter import dump_flat_toml
            return dump_flat_toml(value)

    toml = _Toml()

from .errors import AgentDomainError
from .redaction import redact
from .workspace import AgentWorkspace

_SENSITIVE_KEY = re.compile(r"(?:api[_-]?key|token|password|secret|cookie|private[_-]?key)", re.I)
_PATH_KEYS = {
    "pretrained_model_name_or_path", "vae", "qwen3", "llm_adapter_path", "t5_tokenizer_path",
    "resume", "train_data_dir", "reg_data_dir", "output_dir", "logging_dir", "network_weights",
    "sample_prompts", "dit", "text_encoder", "turbo_dit",
}


def _hash(value: bytes | str) -> str:
    raw = value.encode() if isinstance(value, str) else value
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _json_canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _canonical_toml(value: dict[str, Any]) -> str:
    """Serialize deterministic TOML after recursively sorting mapping keys."""
    def sort_map(item: Any) -> Any:
        if isinstance(item, dict):
            return {key: sort_map(item[key]) for key in sorted(item)}
        if isinstance(item, list):
            return [sort_map(child) for child in item]
        return item

    try:
        return toml.dumps(sort_map(value)).replace("\r\n", "\n")
    except Exception as exc:
        raise AgentDomainError("CONFIG_COMMIT_FAILED", "Canonical TOML serialization failed.", details={"reason": str(exc)}) from None


@dataclass
class TrainingConfigDraft:
    artifact_id: str
    session_id: str
    primary_format: str
    content_hash: str
    target: dict[str, str]
    source_template_id: str | None = None
    source_template_version: str | None = None
    user_inputs: dict[str, Any] = field(default_factory=dict)
    skill_sources: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    confidence: float | None = None
    missing_inputs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class TrainingConfigArtifactService:
    """TrainingConfigArtifact v1 service shared by Agent and manual import."""

    def __init__(
        self,
        workspace: AgentWorkspace,
        *,
        project_root: str | os.PathLike[str] | None = None,
        validator: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
        normalizer: Callable[[dict[str, Any], str], tuple[dict[str, Any], list[str]]] | None = None,
        preflight: Callable[[dict[str, Any], str], Any] | None = None,
    ) -> None:
        self.workspace = workspace
        self.project_root = Path(project_root or os.getcwd()).absolute()
        self.validator = validator
        self.normalizer = normalizer
        self.preflight = preflight
        self._validations: dict[str, dict[str, Any]] = {}

    def get_template(self, page_train_type: str, *, template_id: str | None = None) -> dict[str, Any]:
        if not isinstance(page_train_type, str) or not page_train_type.strip():
            raise AgentDomainError("CONFIG_SCHEMA_INVALID", "Training type is required.")
        schema = self._schema_summary(page_train_type)
        return {
            "templateId": template_id or f"training-config:{page_train_type}",
            "templateVersion": "v1",
            "pageTrainType": page_train_type,
            "schemaVersion": "v1",
            "allowedFormats": ["toml", "json"],
            "requiredFields": ["model_train_type"],
            "allowedFields": schema.get("allowedFields", []),
            "environment": {"credentials": "configured", "workspace": self.workspace.manifest.session_id},
        }

    def validate_draft(
        self,
        artifact_path: str,
        *,
        page_train_type: str,
        baseline_artifact: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if Path(artifact_path).suffix.lower() not in {".toml", ".json"}:
            raise AgentDomainError("CONFIG_FORMAT_MISMATCH", "Only TOML and JSON drafts are supported.")
        raw = self.workspace.read_bytes(artifact_path)
        content_hash = _hash(raw)
        config, fmt = self._parse(raw, Path(artifact_path).suffix.lower())
        self._reject_sensitive(config)
        self._reject_forbidden_paths(config)
        if self.validator:
            imported = self.validator(page_train_type, deepcopy(config))
        else:
            from mikazuki.utils.config_import import validate_config_import
            imported = validate_config_import(page_train_type, deepcopy(config))
        result_name = imported.get("result") if isinstance(imported, dict) else None
        if result_name == "reject":
            code = self._map_import_error(imported)
            raise AgentDomainError(code, "Training configuration import validation failed.", details={"errors": imported.get("errors", [])})
        normalized = deepcopy(imported.get("config", config)) if isinstance(imported, dict) else deepcopy(config)
        warnings = list(imported.get("warnings", [])) if isinstance(imported, dict) else []
        if self.normalizer:
            normalized, normalize_warnings = self.normalizer(deepcopy(normalized), page_train_type)
            warnings.extend(normalize_warnings)
        else:
            try:
                from mikazuki.utils.config_export import normalize_config_for_export
                normalized, normalize_warnings = normalize_config_for_export(deepcopy(normalized), page_train_type=page_train_type)
                warnings.extend(normalize_warnings)
            except Exception as exc:
                raise AgentDomainError("CONFIG_SCHEMA_INVALID", "Training configuration normalization failed.", details={"reason": str(exc)}) from None
        semantic_diff = self._semantic_diff(config, normalized)
        validation_hash = _hash(_json_canonical({"artifact": content_hash, "normalized": normalized, "pageTrainType": page_train_type}))
        source_revision = self.workspace.manifest.source_revision or "workspace:" + self.workspace.manifest.session_id
        output = {
            "state": "preflight-pass",
            "artifactId": (metadata or {}).get("artifact_id") or str(uuid.uuid4()),
            "primaryFormat": fmt,
            "contentHash": content_hash,
            "validationHash": validation_hash,
            "sourceRevision": source_revision,
            "target": {"modelTrainType": str(normalized.get("model_train_type") or page_train_type), "engine": "next-trainer"},
            "normalizedConfig": redact(normalized),
            "semanticDiff": semantic_diff,
            "warnings": warnings,
            "provenance": {
                "templateId": (metadata or {}).get("source_template_id"),
                "skillSources": list((metadata or {}).get("skill_sources", [])),
                "assumptions": list((metadata or {}).get("assumptions", [])),
                "confidence": (metadata or {}).get("confidence"),
                "missingInputs": list((metadata or {}).get("missing_inputs", [])),
            },
        }
        if self.preflight:
            check = self.preflight(deepcopy(normalized), page_train_type)
            ok = bool(check if isinstance(check, bool) else getattr(check, "ok", True))
            if not ok:
                errors = list(getattr(check, "errors", []) or [])
                raise AgentDomainError("CONFIG_PREFLIGHT_FAILED", "Training configuration preflight failed.", details={"errors": errors})
        self._validations[validation_hash] = {"artifactPath": artifact_path, "contentHash": content_hash, "sourceRevision": source_revision, "normalized": normalized, "result": output}
        return output

    def commit_draft(
        self,
        validation_hash: str,
        *,
        confirmation_ticket: dict[str, Any] | None = None,
        source_revision: str | None = None,
        canonical_dir: str | os.PathLike[str] | None = None,
    ) -> dict[str, Any]:
        validation = self._validations.get(validation_hash)
        if validation is None:
            raise AgentDomainError("CONFIG_CONFIRMATION_MISMATCH", "Validation result was not found.", status_code=409)
        if not confirmation_ticket or confirmation_ticket.get("state") != "approved":
            raise AgentDomainError("CONFIG_CONFIRMATION_REQUIRED", "An approved confirmation ticket is required.", status_code=409)
        if source_revision and source_revision != validation["sourceRevision"]:
            raise AgentDomainError("CONFIG_SOURCE_CHANGED", "The source revision changed.", status_code=409)
        artifact_path = validation["artifactPath"]
        current_hash = self.workspace.file_hash(artifact_path)
        if current_hash != validation["contentHash"]:
            raise AgentDomainError("CONFIG_SOURCE_CHANGED", "The draft changed after validation.", status_code=409)
        target_dir = Path(canonical_dir or (self.project_root / "config" / "autosave")).absolute()
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise AgentDomainError("CONFIG_COMMIT_FAILED", "Canonical configuration directory is unavailable.") from None
        canonical = _canonical_toml(validation["normalized"])
        config_id = datetime.now(timezone.utc).strftime("agent-%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:12]
        target = target_dir / f"{config_id}.toml"
        tmp = target.with_suffix(".toml.tmp")
        try:
            with open(tmp, "x", encoding="utf-8", newline="\n") as handle:
                handle.write(canonical)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, target)
        except FileExistsError:
            raise AgentDomainError("CONFIG_COMMIT_FAILED", "Canonical configuration collision.", retryable=True) from None
        except OSError as exc:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise AgentDomainError("CONFIG_COMMIT_FAILED", "Canonical configuration could not be written.", details={"reason": str(exc)}) from None
        canonical_hash = _hash(canonical)
        audit_id = "audit-" + uuid.uuid4().hex
        return {
            "state": "committed",
            "configId": config_id,
            "pathAlias": f"config/autosave/{target.name}",
            "contentHash": canonical_hash,
            "auditId": audit_id,
            "ticketId": confirmation_ticket.get("ticketId"),
            "warnings": validation["result"].get("warnings", []),
            "autoRun": False,
        }

    @staticmethod
    def _parse(raw: bytes, suffix: str) -> tuple[dict[str, Any], str]:
        try:
            text = raw.decode("utf-8")
            value = json.loads(text) if suffix == ".json" else toml.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, toml.TomlDecodeError if hasattr(toml, "TomlDecodeError") else ValueError) as exc:
            raise AgentDomainError("CONFIG_PARSE_ERROR", "The configuration draft could not be parsed.", details={"reason": str(exc)}) from None
        if not isinstance(value, dict):
            raise AgentDomainError("CONFIG_FORMAT_MISMATCH", "The configuration root must be an object/table.")
        return value, suffix[1:]

    @staticmethod
    def _reject_sensitive(value: Any, prefix: str = "") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if _SENSITIVE_KEY.search(str(key)):
                    raise AgentDomainError("CONFIG_SENSITIVE_FIELD_REJECTED", "Credential fields are not allowed in drafts.", details={"field": prefix + str(key)})
                TrainingConfigArtifactService._reject_sensitive(child, prefix + str(key) + ".")
        elif isinstance(value, list):
            for child in value:
                TrainingConfigArtifactService._reject_sensitive(child, prefix)

    @staticmethod
    def _reject_forbidden_paths(value: Any, prefix: str = "") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                field = f"{prefix}.{key}" if prefix else str(key)
                if str(key) in _PATH_KEYS and isinstance(child, str):
                    path = child.strip()
                    if path.startswith(("/", "\\\\")) or re.match(r"^[A-Za-z]:[\\/].*", path):
                        raise AgentDomainError("CONFIG_PATH_UNBOUND", "Absolute training paths must be selected through host resource bindings.", details={"field": field})
                TrainingConfigArtifactService._reject_forbidden_paths(child, field)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                TrainingConfigArtifactService._reject_forbidden_paths(child, f"{prefix}[{index}]")

    @staticmethod
    def _semantic_diff(source: dict[str, Any], normalized: dict[str, Any]) -> list[dict[str, Any]]:
        diff: list[dict[str, Any]] = []
        keys = sorted(set(source) | set(normalized))
        for key in keys:
            if source.get(key) != normalized.get(key):
                diff.append({"field": key, "before": redact(source.get(key)), "after": redact(normalized.get(key))})
        return diff

    @staticmethod
    def _map_import_error(result: dict[str, Any]) -> str:
        message = " ".join(str(item) for item in result.get("errors", []))
        if "未知" in message or "unknown" in message.lower():
            return "CONFIG_UNKNOWN_FIELD"
        if "路径" in message or "path" in message.lower():
            return "CONFIG_PATH_UNBOUND"
        return "CONFIG_IMPORT_INCOMPATIBLE"

    @staticmethod
    def _schema_summary(page_train_type: str) -> dict[str, Any]:
        root = Path.cwd() / "mikazuki" / "schema"
        candidates = [root / f"{page_train_type}.ts", root / "shared.ts"]
        text = "\n".join(path.read_text(encoding="utf-8") for path in candidates if path.exists())
        fields = sorted(set(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\??\s*:", text, re.MULTILINE)))
        return {"allowedFields": fields}


__all__ = ["TrainingConfigArtifactService", "TrainingConfigDraft"]

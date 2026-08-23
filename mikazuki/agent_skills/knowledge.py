from __future__ import annotations

import re
from dataclasses import replace
from typing import Iterable
from urllib.parse import urlparse

from .errors import AgentSkillError, ErrorCode
from .models import Confidence, EvidenceType, KnowledgeDocument, KnowledgeResult, SourceRef


_TOKEN_RE = re.compile(r"[\w.-]+", re.UNICODE)


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in _TOKEN_RE.findall(value or "") if token}


class KnowledgeStore:
    """Small deterministic source-index used by the plugin's read-only tool.

    This is intentionally not an embedding/vector database.  A later storage
    implementation can preserve this contract while keeping every hit tied to
    an explicit source revision and scope.
    """

    def __init__(self, documents: Iterable[KnowledgeDocument] = ()) -> None:
        self._documents: dict[str, KnowledgeDocument] = {}
        for document in documents:
            self.add(document)

    @property
    def documents(self) -> tuple[KnowledgeDocument, ...]:
        return tuple(self._documents.values())

    def add(self, document: KnowledgeDocument) -> None:
        source = document.source
        parsed = urlparse(source.url)
        if not source.source_id or not source.title or parsed.scheme not in {"https", "http"}:
            raise AgentSkillError(ErrorCode.OFFICIAL_SOURCE_REQUIRED, "knowledge source metadata is invalid")
        if not document.text.strip():
            raise AgentSkillError(ErrorCode.INVALID_RECORD, "knowledge document is empty")
        self._documents[source.source_id] = document

    def search(
        self,
        query: str,
        *,
        model_family: str | None = None,
        lora_category: str | None = None,
        engine: str | None = None,
        top_k: int = 10,
    ) -> list[KnowledgeResult]:
        if not isinstance(query, str) or not query.strip() or not 1 <= top_k <= 10:
            raise AgentSkillError(ErrorCode.INVALID_QUERY, "query and top_k are invalid")
        query_tokens = _tokens(query)
        filters = _tokens(" ".join(x for x in (model_family, lora_category, engine) if x))
        ranked: list[tuple[int, KnowledgeDocument]] = []
        for doc in self._documents.values():
            corpus = _tokens(f"{doc.source.title} {doc.text} {' '.join(doc.tags)}")
            if filters and not filters <= corpus:
                continue
            score = len(query_tokens & corpus)
            if score:
                ranked.append((score, doc))
        ranked.sort(key=lambda item: (-item[0], item[1].source.source_id))
        return [self._result(doc, score, query_tokens) for score, doc in ranked[:top_k]] or [
            KnowledgeResult(
                source_id=None,
                title="Unknown",
                excerpt="No source-backed answer is available for this query.",
                evidence_type=EvidenceType.UNKNOWN,
                version="unknown",
                scope="unknown",
                confidence=Confidence.UNKNOWN,
                unknown=True,
            )
        ]

    @staticmethod
    def _result(doc: KnowledgeDocument, score: int, query_tokens: set[str]) -> KnowledgeResult:
        # Keep excerpts bounded so untrusted source text cannot flood the chat.
        text = " ".join(doc.text.split())
        excerpt = text[:500] + ("..." if len(text) > 500 else "")
        confidence = Confidence.HIGH if score >= 3 else Confidence.MEDIUM
        if doc.source.evidence_type in {EvidenceType.UNKNOWN, EvidenceType.MODEL_INFERENCE}:
            confidence = Confidence.UNKNOWN if doc.source.evidence_type == EvidenceType.UNKNOWN else Confidence.LOW
        return KnowledgeResult(
            source_id=doc.source.source_id,
            title=doc.source.title,
            excerpt=excerpt,
            evidence_type=doc.source.evidence_type,
            version=doc.source.version or "unknown",
            scope=doc.source.scope or "unknown",
            confidence=confidence,
        )


__all__ = ["KnowledgeStore"]

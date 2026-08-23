from __future__ import annotations

import json
from pathlib import Path

import pytest

from mikazuki.agent_skills import (
    AgentSkillError,
    CivitaiClient,
    CivitaiEvidenceRecord,
    CivitaiQuery,
    Confidence,
    EvidenceType,
    KnowledgeDocument,
    KnowledgeStore,
    SourceRef,
    build_cohort_report,
    draft_skill,
    run_skill_eval,
    validate_skill,
)


FIXTURE = Path(__file__).parent / "fixtures" / "civitai_lora_response.json"


def _transport(payload, statuses=None):
    statuses = list(statuses or [200])
    calls = []

    def call(method, url, params):
        calls.append((method, url, params))
        status = statuses.pop(0) if statuses else 200
        return status, payload, {"Retry-After": "0"}

    call.calls = calls
    return call


def test_query_contract_rejects_unsafe_or_oversized_requests():
    with pytest.raises(AgentSkillError) as exc:
        CivitaiQuery(limit=101).validate()
    assert exc.value.code == "AGENT_SKILL_INVALID_QUERY"
    with pytest.raises(AgentSkillError):
        CivitaiQuery(nsfw=True).validate()
    with pytest.raises(AgentSkillError):
        CivitaiClient(base_url="https://example.invalid/api/v1")


def test_contract_official_api_fixture_preserves_cursor_and_unknowns():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    transport = _transport(payload)
    result = CivitaiClient(transport=transport).search_loras(CivitaiQuery(base_model="SDXL", limit=2))
    assert result["next_cursor"] == "cursor-2"
    assert len(result["records"]) == 2
    disclosed, unknown = result["records"]
    assert disclosed.normalized_parameters["rank"] == 32
    assert unknown.training_details is None
    assert "rank" in unknown.missing_fields
    assert unknown.normalized_parameters["rank"] == "unknown"
    assert transport.calls[0][2]["types"] == "LORA"
    assert transport.calls[0][2]["nsfw"] == "false"


def test_retry_429_is_bounded_and_has_stable_error_after_limit():
    payload = {"items": []}
    sleeps = []
    transport = _transport(payload, statuses=[429, 429, 429])
    client = CivitaiClient(transport=transport, sleep=sleeps.append, max_retries=2)
    with pytest.raises(AgentSkillError) as exc:
        client.search_loras(CivitaiQuery(limit=1))
    assert exc.value.code == "AGENT_SKILL_RATE_LIMITED"
    assert len(transport.calls) == 3
    assert len(sleeps) == 2


def test_knowledge_contract_returns_source_metadata_and_unknown():
    source = SourceRef("train-v1", "Training guide", "https://example.org/guide", "v1", "2026-08-21T00:00:00Z", "SDXL character", EvidenceType.OFFICIAL_DOCUMENTATION)
    store = KnowledgeStore([KnowledgeDocument(source, "SDXL character rank and alpha guidance", ("SDXL", "character"))])
    hit = store.search("rank alpha", model_family="SDXL", lora_category="character")[0]
    assert hit.source_id == "train-v1"
    assert hit.version == "v1"
    assert hit.scope == "SDXL character"
    assert hit.unknown is False
    unknown = store.search("missing topic")[0]
    assert unknown.unknown is True and unknown.source_id is None


def test_cohort_stats_report_missingness_bias_and_exploratory_status():
    records = [
        CivitaiEvidenceRecord(
            source_url=f"https://civitai.com/api/v1/models/{index}", model_id=index,
            creator="same" if index < 4 else f"creator-{index}", base_model="SDXL",
            lora_category="character", stats={"downloadCount": index * 10},
            normalized_parameters={"rank": index, "alpha": "unknown" if index % 2 else index / 2},
        ) for index in range(1, 6)
    ]
    report = build_cohort_report(records, rankings=["Most Downloaded"], time_windows=["AllTime"])
    assert report.status == "exploratory"
    assert report.field_coverage["alpha"] == 0.4
    assert "single_ranking_exposure_bias" in report.bias_flags
    assert "popularity_is_discovery_only" in report.bias_flags
    assert report.creator_concentration["share"] >= 0.5
    assert report.counterexamples


def test_integration_draft_skill_has_citations_and_publish_gate():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    records = CivitaiClient(transport=_transport(payload)).search_loras(CivitaiQuery(limit=2))["records"]
    sources = [SourceRef(
        "civitai:model:101:version:1001", "Civitai record", records[0].source_url,
        records[0].api_version, records[0].retrieved_at, "SDXL character", EvidenceType.API_METADATA,
    )]
    skill = draft_skill(records, sources=sources)
    validation = validate_skill(skill)
    assert validation.valid is True
    assert validation.publishable is False
    assert all(item["source_ids"] for item in skill.recommendations)
    assert "popularity" in " ".join(skill.caveats)


def test_gray_cohort_differs_by_base_model_and_category():
    records = [
        CivitaiEvidenceRecord(source_url="https://civitai.com/api/v1/models/1", model_id=1, base_model="SDXL", lora_category="character", normalized_parameters={"rank": 16}),
        CivitaiEvidenceRecord(source_url="https://civitai.com/api/v1/models/2", model_id=2, base_model="FLUX.1", lora_category="style", normalized_parameters={"rank": 64}),
    ]
    report = build_cohort_report(records)
    assert set(report.cohorts) == {"FLUX.1:style", "SDXL:character"}
    assert report.cohorts["FLUX.1:style"]["fieldCoverage"]["rank"] == 1.0


def test_zero_short_empty_cache_yields_unknown_exploratory_skill():
    report = build_cohort_report([])
    skill = draft_skill([], report=report)
    assert report.status == "exploratory"
    assert skill.validation_status == "unvalidated"
    assert validate_skill(skill).valid is True
    assert run_skill_eval(skill, [{"case_id": "unknown", "expect_unknown": True}])["passed"] == 1


def test_edd_model_inference_cannot_be_a_publishable_source():
    source = SourceRef("inferred", "Inference", "https://example.org/inference", "v1", "now", "unknown", EvidenceType.MODEL_INFERENCE)
    skill = draft_skill([], sources=[source])
    skill.recommendations = [{"parameter": "rank", "source_ids": ["inferred"], "confidence": "low", "rationale": "observed"}]
    skill.validation_status = "validated"
    skill.reviewer = "reviewer"
    result = validate_skill(skill)
    assert result.valid is False
    assert "validated_skill_requires_local_experiment" in result.errors

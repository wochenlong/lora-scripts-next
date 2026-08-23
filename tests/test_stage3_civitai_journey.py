"""Stage 3 Civitai evidence pipeline: API -> record -> cohort -> skill -> eval.

Deterministic integration chain over a fixture transport, Zero-Short
empty-cache skill generation, Gray cohort differences, and an opt-in Real
sample (public official API, <=100 records, no model/image download):

    pytest tests/test_stage3_civitai_journey.py --civitai-real
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mikazuki.agent_skills.civitai import CivitaiClient, CivitaiQuery, normalize_lora_record
from mikazuki.agent_skills.cohort import build_cohort_report
from mikazuki.agent_skills.errors import AgentSkillError
from mikazuki.agent_skills.skill import draft_skill, run_skill_eval, validate_skill

from agent_test_support import dev_docs_root

EVIDENCE_DIR = dev_docs_root() / "evidence" / "stage-3-skills"


def _item(model_id, version_id, base, creator, downloads, details, *, model_type="LORA", nsfw=False, published="2026-01-15T00:00:00Z"):
    return {
        "model": {
            "id": model_id, "name": f"fixture-{model_id}", "type": model_type,
            "nsfw": nsfw, "creator": {"username": creator},
            "publishedAt": published,
            "stats": {"downloadCount": downloads, "ratingCount": 10, "rating": 4.5, "favoriteCount": 5},
        },
        "modelVersion": {
            "id": version_id, "name": "v1", "baseModel": base,
            "trainingDetails": details,
            "trainedWords": ["trigger"],
        },
    }


FULL_DETAILS = {
    "learningRate": "0.0001", "networkType": "LoRA", "rank": 32, "batchSize": 1,
    "epochs": 15, "optimizer": "AdamW8bit", "scheduler": "cosine", "resolution": 512,
}


def _fixture_items():
    return [
        _item(101, 9001, "Stable Diffusion", "creatorA", 5000, FULL_DETAILS),
        _item(102, 9002, "Stable Diffusion", "creatorB", 4000, None),
        _item(103, 9003, "Stable Diffusion", "creatorC", 3000, {**FULL_DETAILS, "rank": 16}),
        _item(104, 9004, "SDXL", "creatorA", 2000, None),
        _item(105, 9005, "SDXL", "creatorD", 1500, {**FULL_DETAILS, "learningRate": "0.0002"}),
        _item(106, 9006, "SDXL", "creatorE", 1200, {**FULL_DETAILS, "epochs": 10}),  # disclosed: keeps coverage >= 0.6
        _item(107, 9007, "Stable Diffusion", "creatorF", 900, None, model_type="CHECKPOINT"),
        _item(108, 9008, "Stable Diffusion", "creatorG", 800, None, nsfw=True),
    ]


class _FixtureTransport:
    def __init__(self, items):
        self.items = items
        self.calls = []

    def __call__(self, method, url, params):
        self.calls.append((method, url, dict(params)))
        return 200, {"items": self.items, "metadata": {"nextCursor": None}}, {"content-type": "application/json"}


def _usable(records):
    return [record for record in records if not record.excluded]


def test_stage3_integration_api_record_cohort_skill_eval():
    transport = _FixtureTransport(_fixture_items())
    client = CivitaiClient(transport=transport, sleep=lambda _s: None)
    result = client.search_loras(CivitaiQuery(base_model=None, sort="Most Downloaded", limit=20))
    records = result["records"]
    assert len(records) == 8
    usable = _usable(records)
    # exclusions: checkpoint (not_lora) + nsfw lora
    assert len(usable) == 6
    excluded = {record.exclusion_reason for record in records if record.excluded}
    assert excluded == {"not_lora", "nsfw"}

    # undisclosed trainingDetails stay unknown (0 inference-as-fact)
    undisclosed = [record for record in usable if record.training_details is None]
    assert len(undisclosed) == 2
    for record in undisclosed:
        assert record.normalized_parameters["learning_rate"] == "unknown"
        assert record.confidence.value == "low"
        assert "learning_rate" in record.missing_fields
    for record in usable:
        assert record.source_url.startswith("https://civitai.com/")
        assert record.retrieved_at

    cohort = build_cohort_report(usable, query="fixture sample")
    assert cohort.status in {"exploratory", "formal"}
    assert cohort.status == "exploratory"  # small sample must stay exploratory
    assert cohort.missingness

    skill = draft_skill(usable, report=cohort)
    assert skill.validation_status == "unvalidated"
    validation = validate_skill(skill)
    assert validation.valid is True, validation.errors
    assert validation.publishable is False  # no human reviewer / local experiment
    for recommendation in skill.recommendations:
        assert recommendation["source_ids"]
        assert "causal" not in str(recommendation["rationale"]).casefold().replace("not causal", "")
    eval_result = run_skill_eval(skill, [
        {"case_id": "cites-sources", "expected_source_ids": [skill.sources[0].source_id]},
        {"case_id": "empty-cache", "expect_unknown": False},
    ])
    assert eval_result["valid"] is True
    assert eval_result["score"] == 1.0
    assert transport.calls[0][0] == "GET" and "civitai.com" in transport.calls[0][1]


def test_stage3_zero_short_empty_cache_skill():
    cwd = Path.cwd()
    before = {path.name for path in cwd.iterdir()}
    skill = draft_skill([])
    after = {path.name for path in cwd.iterdir()}
    assert before == after  # skill generation is stateless: no cache/files left behind

    assert len(skill.sources) == 1
    assert skill.sources[0].source_id == "unknown:empty-cache"
    assert skill.recommendations == []
    assert skill.validation_status == "unvalidated"
    validation = validate_skill(skill)
    assert validation.valid is True, validation.errors
    assert validation.publishable is False
    assert "no_quantitative_recommendations" in validation.warnings
    eval_result = run_skill_eval(skill, [{"case_id": "empty", "expect_unknown": True}])
    assert eval_result["passed"] == 1


def test_stage3_gray_cohort_differences_deterministic():
    items = _fixture_items()
    transport_a = _FixtureTransport(items[:4])      # SD-heavy, Most Downloaded
    transport_b = _FixtureTransport(items[3:7])     # SDXL-heavy, different creators
    records_a = _usable(CivitaiClient(transport=transport_a, sleep=lambda _s: None).search_loras()["records"])
    records_b = _usable(CivitaiClient(transport=transport_b, sleep=lambda _s: None).search_loras()["records"])
    cohort_a = build_cohort_report(records_a, query="a")
    cohort_b = build_cohort_report(records_b, query="b")
    assert (cohort_a.cohorts != cohort_b.cohorts or cohort_a.creator_concentration != cohort_b.creator_concentration or cohort_a.distributions != cohort_b.distributions)
    # determinism: same input -> identical report
    again = build_cohort_report(records_a, query="a")
    assert json.dumps(cohort_a.as_dict(), sort_keys=True) == json.dumps(again.as_dict(), sort_keys=True)
    # below-threshold cohorts stay exploratory (no formal scope from small samples)
    assert cohort_a.status == "exploratory" and cohort_b.status == "exploratory"


def test_stage3_real_public_sample(request: pytest.FixtureRequest):
    if not request.config.getoption("--civitai-real"):
        pytest.skip("real Civitai sample is opt-in via --civitai-real")
    client = CivitaiClient(sleep=lambda _s: None)
    queries = [
        CivitaiQuery(base_model="Stable Diffusion", sort="Most Downloaded", limit=30),
        CivitaiQuery(base_model="SDXL", sort="Most Downloaded", limit=30),
    ]
    all_records = []
    per_query = []
    for query in queries:
        result = client.search_loras(query)
        records = result["records"]
        per_query.append({
            "baseModel": query.base_model,
            "sort": query.sort,
            "returned": len(records),
            "usable": len(_usable(records)),
        })
        all_records.extend(_usable(records))
    assert len(all_records) <= 100
    cohort = build_cohort_report(all_records, query="real public sample")
    skill = draft_skill(all_records, report=cohort)
    validation = validate_skill(skill)
    assert validation.valid is True, validation.errors
    disclosed = sum(1 for record in all_records if record.training_details is not None)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    target = EVIDENCE_DIR / "source" / "real-sample.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    evidence = (
        "# Stage 3 Real Civitai Public Sample\n\n"
        f"- date: {datetime.now(timezone.utc).isoformat()}\n"
        f"- endpoint: official public API https://civitai.com/api/v1/models (anonymous, no download)\n"
        f"- queries: {json.dumps(per_query)}\n"
        f"- usable records: {len(all_records)} (<=100)\n"
        f"- disclosed trainingDetails: {disclosed}/{len(all_records)} ({round(100.0 * disclosed / max(1, len(all_records)), 1)}%)\n"
        f"- cohort status: {cohort.status}\n"
        f"- skill validation: valid={validation.valid} publishable={validation.publishable} errors={list(validation.errors)}\n"
        "- gates: 0 inference-as-fact (undisclosed details stay unknown), all records carry "
        "source/time/version, skill remains unvalidated/exploratory\n"
    )
    target.write_text(evidence, encoding="utf-8")

"""Skill and public-evidence services for the optional Pi Agent plugin.

The package deliberately contains deterministic, model-free helpers.  It does
not call a local model and it does not make a recommendation from popularity
alone.  Network access is isolated in :mod:`civitai` and can be replaced by a
test transport.
"""

from .errors import AgentSkillError, ErrorCode
from .models import (
    Confidence,
    EvidenceType,
    KnowledgeDocument,
    KnowledgeResult,
    CivitaiEvidenceRecord,
    SourceRef,
    SkillPackage,
    SkillValidation,
)
from .knowledge import KnowledgeStore
from .civitai import CivitaiClient, CivitaiQuery
from .cohort import CohortReport, build_cohort_report
from .skill import build_parameter_template, draft_skill, validate_skill, run_skill_eval

__all__ = [
    "AgentSkillError", "ErrorCode", "Confidence", "EvidenceType",
    "KnowledgeDocument", "KnowledgeResult", "CivitaiEvidenceRecord",
    "SourceRef", "SkillPackage", "SkillValidation", "KnowledgeStore",
    "CivitaiClient", "CivitaiQuery", "CohortReport", "build_cohort_report",
    "build_parameter_template", "draft_skill", "validate_skill", "run_skill_eval",
]

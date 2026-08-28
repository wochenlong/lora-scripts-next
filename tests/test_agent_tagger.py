from __future__ import annotations

"""Host-Tool adapter for the tagger batch job (mikazuki.agent_tagger).

Covers: catalog visibility under the caption-commit permission, the two-stage
confirmation gate (no job starts before approval), model/parameter validation,
the busy guard, cooperative cancel (idempotent) and progress snapshots.

The real ``run_interrogate_job`` (ONNX model) is monkeypatched; only the
``tagger_progress`` singleton lifecycle is exercised for real.
"""

import asyncio
import threading
from types import SimpleNamespace

import pytest

import mikazuki.agent_tagger as agent_tagger
from mikazuki.agent_tagger import TaggerToolError, cancel_tagger_job, start_tagger_job, tagger_status
from mikazuki.plugin_host.agent_tools import AgentToolService
from mikazuki.plugin_host.confirmation import ConfirmationTicketStore
from mikazuki.tagger.progress import tagger_progress

ALL_PERMISSIONS = frozenset({
    "model-provider",
    "training-config",
    "dataset-review",
    "caption-commit",
    "metrics-read",
    "artifacts-read",
    "external-civitai-read",
})
_TAGGER_TOOLS = {"tagger_start", "tagger_cancel", "tagger_status"}


class _StubMarketplaceManager:
    def capability_context(self, plugin_id: str):
        return SimpleNamespace(granted_permissions=ALL_PERMISSIONS)

    def plugin_for_host_tool_token(self, token: str):
        return "plugin"


def _patch_manager(monkeypatch):
    import mikazuki.plugin_marketplace.api as marketplace_api

    monkeypatch.setattr(marketplace_api, "_manager", _StubMarketplaceManager(), raising=False)


class _FakeJob:
    """Controllable stand-in for run_interrogate_job driving the real progress singleton."""

    def __init__(self) -> None:
        self.calls: list = []
        self.ready = threading.Event()
        self.release = threading.Event()
        self.block = True

    def run(self, req) -> None:
        self.calls.append(req)
        if not tagger_progress.try_begin("tagging", req.interrogator_model, "fake"):
            self.ready.set()
            return
        tagger_progress.begin_tagging(req.interrogator_model, 5)
        self.ready.set()
        if self.block:
            self.release.wait(timeout=10)
        if tagger_progress.is_cancel_requested():
            tagger_progress.finish_cancelled()
        else:
            tagger_progress.finish_success("done")

    def release_job(self) -> None:
        self.release.set()


@pytest.fixture(autouse=True)
def _clean_tagger_state():
    yield
    # Belt and braces: leave the global singleton idle for the next test even if
    # a test left a job blocked (its thread will finish against a released state).
    tagger_progress.reset_idle()


def test_catalog_exposes_tagger_tools_only_with_caption_commit():
    service = AgentToolService(ConfirmationTicketStore())
    with_perm = {item["name"] for item in service.definitions(frozenset({"caption-commit"}))}
    assert _TAGGER_TOOLS <= with_perm
    without_perm = {item["name"] for item in service.definitions(frozenset({"dataset-review"}))}
    assert not (_TAGGER_TOOLS & without_perm)


def test_start_requires_confirmation_before_job_launches(monkeypatch):
    _patch_manager(monkeypatch)
    fake = _FakeJob()
    fake.block = False
    monkeypatch.setattr(agent_tagger, "run_interrogate_job", fake.run)

    store = ConfirmationTicketStore()
    service = AgentToolService(store)

    first = asyncio.run(service.invoke("plugin", "s1", "call-1", "tagger_start", {"path": "imgs"}))
    assert first["state"] == "confirmation_required"
    assert first["ticket"]["toolCallId"] == "call-1"
    assert fake.calls == []  # no job launched before approval

    ticket_id = first["ticket"]["ticketId"]
    store.resolve(ticket_id, "approved")
    second = asyncio.run(
        service.invoke("plugin", "s1", "call-1", "tagger_start", {"path": "imgs", "confirmationTicketId": ticket_id})
    )
    assert second["state"] == "started"
    assert second["model"] == "wd14-convnextv2-v2"
    assert second["path"] == "imgs"
    assert fake.ready.wait(5), "tagger job thread did not start"
    assert len(fake.calls) == 1
    assert fake.calls[0].path == "imgs"


def test_start_rejects_unknown_model():
    with pytest.raises(TaggerToolError) as exc:
        start_tagger_job({"path": "imgs", "interrogator_model": "does-not-exist"})
    assert exc.value.code == "TAGGER_MODEL_UNKNOWN"
    assert exc.value.status_code == 400


@pytest.mark.parametrize("bad", [2.0, -0.1, "high", True])
def test_start_rejects_invalid_threshold(bad):
    with pytest.raises(TaggerToolError) as exc:
        start_tagger_job({"path": "imgs", "threshold": bad})
    assert exc.value.code == "TAGGER_PARAMS_INVALID"


@pytest.mark.parametrize("bad", [12.0, "yes", None])
def test_start_rejects_invalid_bool(bad):
    with pytest.raises(TaggerToolError) as exc:
        start_tagger_job({"path": "imgs", "add_rating_tag": bad})
    assert exc.value.code == "TAGGER_PARAMS_INVALID"


def test_start_rejects_empty_path():
    with pytest.raises(TaggerToolError) as exc:
        start_tagger_job({"path": "   "})
    assert exc.value.code == "TAGGER_PARAMS_INVALID"


def test_start_refuses_when_another_job_is_busy(monkeypatch):
    fake = _FakeJob()
    monkeypatch.setattr(agent_tagger, "run_interrogate_job", fake.run)
    try:
        first = start_tagger_job({"path": "imgs"})
        assert first["state"] == "started"
        assert fake.ready.wait(5), "first job did not become busy"
        with pytest.raises(TaggerToolError) as exc:
            start_tagger_job({"path": "other"})
        assert exc.value.code == "TAGGER_BUSY"
        assert exc.value.status_code == 409
        assert len(fake.calls) == 1  # the second start never launched a job
    finally:
        fake.release_job()


def test_cancel_is_idempotent_when_idle():
    result = cancel_tagger_job()
    assert result["cancelled"] is False
    assert result["state"] == "idle"


def test_cancel_requests_cooperative_cancel_when_busy(monkeypatch):
    fake = _FakeJob()
    monkeypatch.setattr(agent_tagger, "run_interrogate_job", fake.run)
    try:
        start_tagger_job({"path": "imgs"})
        assert fake.ready.wait(5)
        result = cancel_tagger_job()
        assert result["cancelled"] is True
        assert result["state"] == "cancelling"
        fake.release_job()
        # the fake observes the cancel request and reports the cancelled finish
        tagger_progress.finish_cancelled()
    finally:
        fake.release_job()


def test_status_reports_idle_with_snapshot():
    result = tagger_status()
    assert result["state"] == "idle"
    assert result["snapshot"]["phase"] == "idle"

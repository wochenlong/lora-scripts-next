"""Regression gates for the Copilot PR #308 review findings (C-5/C-6/C-8/C-10).

One focused test per fix, in the review-item order of
development-docs/evidence/pr308-review-20260830/ANALYSIS-PLAN.md.
(C-1's regressions live in tests/test_agent_workspace_api.py.)
"""

import asyncio
import tempfile
from pathlib import Path

from fastapi import HTTPException

from mikazuki.agent_dataset.audit import DatasetInventory, InventoryItem, select_review_sample
from mikazuki.plugin_host import agent_tools
from mikazuki.plugin_host.agent_tools import _Tool, _object, _str, AgentToolService
from mikazuki.plugin_host.confirmation import ConfirmationTicketStore


# --- C-6: limit=0 must select nothing, not one image ---------------------

def _inventory(count: int = 3) -> DatasetInventory:
    images = tuple(
        InventoryItem(item_id=f"i{k}", relative_path=f"img{k}.png", kind="image", bytes=10, content_hash=f"h{k}")
        for k in range(count)
    )
    return DatasetInventory(root="ds", files=images, duplicate_groups=(), caption_distribution={}, total_bytes=10 * count, scan_hash="s")


def test_select_review_sample_honors_zero_limit():
    assert select_review_sample(_inventory(), limit=0) == ()
    assert len(select_review_sample(_inventory(3), limit=2)) == 2


# --- C-5: the sandboxed TemporaryDirectory must leave no leaked directory --

def test_safe_temporary_directory_leaves_no_orphans():
    base = Path(__file__).resolve().parents[1] / ".runtime" / "pytest-tmp"
    base.mkdir(parents=True, exist_ok=True)
    before = {p.name for p in base.iterdir()}
    with tempfile.TemporaryDirectory(prefix="leakcheck") as name:
        created = Path(name)
        assert created.parent == base, "tempdir must stay inside the workspace-safe base"
        assert created.exists(), "the directory must exist for the duration of the context"
        (created / "payload.txt").write_text("x", encoding="utf-8")
    assert not created.exists(), "context exit must remove the directory"
    assert {p.name for p in base.iterdir()} == before


# --- C-8: one approved ticket executes its side effect exactly once -------

def _race_service(monkeypatch):
    calls: list[dict] = []

    async def handler(session: str, call: str, params: dict):
        calls.append(params)
        await asyncio.sleep(0.05)  # interleave point: the loser must already be rejected here
        return {"ok": True}

    tool = _Tool(
        "fake_write", "Fake write", "test double", "training-config", "write",
        _object({"payload": _str(), "confirmationTicketId": {"type": "string"}}, ("payload",)), handler,
    )
    store = ConfirmationTicketStore()
    service = AgentToolService(store)
    monkeypatch.setattr(service, "_tools", lambda: {"fake_write": tool})
    monkeypatch.setattr(agent_tools, "_granted_permissions", lambda plugin_id: frozenset({"training-config"}))
    return service, store, calls


def test_concurrent_retries_of_one_ticket_run_the_handler_once(monkeypatch):
    service, store, calls = _race_service(monkeypatch)
    params = {"payload": "p1"}
    first = asyncio.run(service.invoke("plug", "s", "call-1", "fake_write", dict(params)))
    assert first["state"] == "confirmation_required"
    ticket_id = first["ticket"]["ticketId"]
    store.resolve(ticket_id, "approved")

    async def race():
        async def attempt(tag: str):
            try:
                return await service.invoke("plug", "s", f"call-{tag}", "fake_write", {**params, "confirmationTicketId": ticket_id})
            except HTTPException as exc:
                return exc
        return await asyncio.gather(attempt("a"), attempt("b"))

    outcomes = asyncio.run(race())
    assert sum(1 for item in outcomes if isinstance(item, dict)) == 1
    loser = [item for item in outcomes if isinstance(item, HTTPException)]
    assert len(loser) == 1 and loser[0].status_code == 409
    assert len(calls) == 1, "the side-effecting handler must run exactly once per approved ticket"


def test_failed_execution_releases_the_claim_for_retry(monkeypatch):
    service, store, calls = _race_service(monkeypatch)
    first = asyncio.run(service.invoke("plug", "s", "call-1", "fake_write", {"payload": "p1"}))
    ticket_id = first["ticket"]["ticketId"]
    store.resolve(ticket_id, "approved")

    original = service._tools  # noqa: SLF001 - deliberate test double wiring

    def failing_tools():
        tool = original()["fake_write"]
        return {"fake_write": _Tool(tool.name, tool.label, tool.description, tool.permission, "write", tool.parameters, _raising_handler)}

    async def _raising_handler(session, call, params):
        raise RuntimeError("transient backend fault")

    monkeypatch.setattr(service, "_tools", failing_tools)
    try:
        asyncio.run(service.invoke("plug", "s", "call-x", "fake_write", {"payload": "p1", "confirmationTicketId": ticket_id}))
        raise AssertionError("the failing handler must surface as an error")
    except HTTPException:
        pass
    # The approval survived the failed attempt and is executable again.
    monkeypatch.setattr(service, "_tools", original)
    result = asyncio.run(service.invoke("plug", "s", "call-y", "fake_write", {"payload": "p1", "confirmationTicketId": ticket_id}))
    assert result == {"ok": True}
    assert len(calls) == 1
    # Consumed on success: the retry path is now closed.
    try:
        asyncio.run(service.invoke("plug", "s", "call-z", "fake_write", {"payload": "p1", "confirmationTicketId": ticket_id}))
        raise AssertionError("consumed ticket must be rejected")
    except HTTPException as exc:
        assert exc.status_code == 409


# --- C-10: declared schema bounds are enforced before any handler runs ----

def test_tool_params_are_validated_against_declared_bounds(monkeypatch):
    service = AgentToolService(ConfirmationTicketStore())
    monkeypatch.setattr(agent_tools, "_granted_permissions", lambda plugin_id: frozenset({
        "dataset-review", "external-civitai-read",
    }))

    cases = [
        # (tool, params, expected fragment)
        ("dataset_review_images", {"root": "ds", "limit": 101}, "limit: above maximum 100"),
        ("dataset_review_images", {"root": "ds", "limit": -1}, "limit: below minimum 0"),
        ("dataset_inventory", {"maxFiles": 5, "evil": 1}, "root: required"),
        ("civitai_fetch_version", {"versionIds": list(range(6))}, "exceeds maxItems 5"),
        ("civitai_fetch_version", {"versionIds": ["x"]}, "[0]: expected integer"),
        ("dataset_review_images", {"root": "ds", "model": {"model": "m", "vision": "yes"}}, "vision: expected boolean"),
    ]
    for index, (tool, params, fragment) in enumerate(cases):
        try:
            asyncio.run(service.invoke("plug", f"s{index}", f"c{index}", tool, params))
            raise AssertionError(f"{tool} {params} must be rejected before the handler runs")
        except HTTPException as exc:
            assert exc.status_code == 400, (tool, exc.detail)
            assert exc.detail["code"] == "TOOL_PARAMS_INVALID", (tool, exc.detail)
            assert any(fragment in violation for violation in exc.detail["violations"]), (tool, exc.detail)


def test_curve_series_validation_accepts_every_handler_supported_point_shape():
    from mikazuki.plugin_host.agent_tools import _validate_tool_params

    service = AgentToolService(ConfirmationTicketStore())
    schema = service._tools()["curve_analyze"].parameters
    assert _validate_tool_params(schema, {"series": [[1, 0.9], [2, 0.8]]}) == []
    assert _validate_tool_params(schema, {"series": [{"step": 1, "value": 0.9}, {"x": 2, "y": 0.8}]}) == []
    assert _validate_tool_params(schema, {"series": ["nope"]}) != []
    assert _validate_tool_params(schema, {"series": [["a", 1]]}) != []

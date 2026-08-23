"""Stage 2 real-stack journey: Agent draft -> validate -> confirm -> canonical TOML.

Real (fake trainer) + manual-import parity + Zero-Short, all local:
real FastAPI host, real Host Tool gateway, real TrainingConfigArtifactService,
real confirmation REST, fake trainer that loads the committed TOML through the
same import/normalize chain the trainer uses.  No LLM provider is called.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import httpx
import pytest
import toml

from agent_test_support import (
    PLUGIN_ID,
    HostApp,
    build_entry,
    build_package,
    free_port,
    require_dist,
    workspace_tempdir,
)
from agent_test_support import HOST_VERSION, PLATFORM, SIGNING_KEY, SIGNING_KEY_ID
from mikazuki.agent_workspace import ensure_workspace, get_artifact_service
from mikazuki.agent_workspace.api import _artifact_services
from mikazuki.agent_workspace.artifacts import TrainingConfigArtifactService
from mikazuki.agent_workspace.api import _artifact_services
from mikazuki.agent_workspace.artifacts import TrainingConfigArtifactService
from mikazuki.plugin_host.runtime import ExecutablePluginRuntime
from mikazuki.plugin_marketplace.manager import MarketplaceManager
from mikazuki.plugin_marketplace.paths import MarketplacePaths
from mikazuki.plugin_marketplace.store import MarketplaceStore
from mikazuki.plugin_marketplace.trust import TrustStore
from mikazuki.utils.config_export import normalize_config_for_export
from mikazuki.utils.config_import import validate_config_import

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SESSION = "stage2-session"


def _manager(root: Path, app_port: int) -> MarketplaceManager:
    paths = MarketplacePaths(root / "marketplace")
    return MarketplaceManager(
        paths=paths,
        store=MarketplaceStore(paths.registry_file),
        trust=TrustStore({SIGNING_KEY_ID: ("next-trainer-project", SIGNING_KEY)}),
        host_version=HOST_VERSION,
        platform=PLATFORM,
        runtime=ExecutablePluginRuntime(
            startup_timeout=30,
            host_tool_base_url=f"http://127.0.0.1:{app_port}/api",
        ),
    )


def _make_draft_files(root: Path) -> dict:
    """Create fixture assets under project .runtime; draft uses project-relative paths.

    Host Tools resolve paths against the host cwd (the project root, which
    also provides mikazuki/schema); absolute training paths are rejected as
    CONFIG_PATH_UNBOUND unless host resource bindings are used.
    """
    rel = ".runtime/stage2-" + uuid.uuid4().hex[:8]
    data_dir = PROJECT_ROOT / rel / "dataset" / "1_class"
    data_dir.mkdir(parents=True)
    (data_dir / "sample.txt").write_text("caption placeholder", encoding="utf-8")
    model_dir = PROJECT_ROOT / rel / "sd-models" / "sd15"
    model_dir.mkdir(parents=True)
    (model_dir / "model_index.json").write_text("{}", encoding="utf-8")
    return {
        "model_train_type": "sd-lora",
        "train_data_dir": rel + "/dataset/1_class",
        "pretrained_model_name_or_path": rel + "/sd-models/sd15",
        "output_dir": rel + "/output",
        "output_name": "stage2-agent-lora",
        "enable_preview": False,
    }


def _draft_toml(draft: dict) -> str:
    import toml as _toml
    return _toml.dumps(draft)


def _fake_trainer(script: Path, config_path: Path) -> int:
    """Run the committed TOML through the trainer's import/normalize chain."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    proc = subprocess.run(
        [sys.executable, str(script), str(config_path)],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "FAKE_TRAINER_ACCEPT" in proc.stdout
    return proc.returncode


FAKE_TRAINER = '''
import sys
import toml
from mikazuki.utils.config_import import validate_config_import
from mikazuki.utils.config_export import normalize_config_for_export

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    config = toml.load(handle)
imported = validate_config_import("sd-lora", config)
assert imported["result"] == "ok", imported
normalized, _ = normalize_config_for_export(imported["config"], page_train_type="sd-lora")
assert normalized.get("model_train_type") == "sd-lora"
print("FAKE_TRAINER_ACCEPT", normalized.get("output_name"))
'''


def _write_fake_trainer(root: Path) -> Path:
    script = root / "fake_trainer.py"
    script.write_text(FAKE_TRAINER, encoding="utf-8")
    return script


def _install_enabled(manager, root, client):
    manifest = json.loads((PROJECT_ROOT / "plugin-packages" / PLUGIN_ID / "plugin.json").read_text(encoding="utf-8"))
    package = build_package(root, version="0.4.0")
    entry = build_entry(package, version="0.4.0")
    manager.install(entry, package)
    enabled = manager.enable(PLUGIN_ID, set(manifest["permissions"]))
    assert enabled.enabled is True and enabled.runtime_state == "running"
    return manifest


def _resolve_pending(client, expected_call_id):
    """Approve exactly the pending ticket bound to one Tool call.

    The confirmation store is host-process scoped and shared across tests,
    so tickets are matched by toolCallId instead of assuming a single
    pending ticket.
    """
    response = client.get("/api/plugin-host/confirmations/pending")
    assert response.status_code == 200, response.text
    pending = response.json()["data"]["confirmations"]
    matches = [t for t in pending if t["toolCallId"] == expected_call_id]
    assert len(matches) == 1, (expected_call_id, pending)
    ticket = matches[0]
    resolve = client.post(f"/api/plugin-host/confirmations/{ticket['ticketId']}/resolve", json={"decision": "approved"})
    assert resolve.status_code == 200, resolve.text
    resolved = resolve.json()["data"]
    assert resolved["state"] == "approved"
    return ticket["ticketId"]


def test_stage2_training_journey_fake_trainer_and_parity():
    require_dist()
    old_cwd = os.getcwd()
    try:
        with workspace_tempdir("stage2-journey-") as root:
            os.chdir(PROJECT_ROOT)
            workspace = ensure_workspace(SESSION, purpose="training-config")
            _artifact_services[SESSION] = TrainingConfigArtifactService(workspace, project_root=root)
            app_port = free_port()
            manager = _manager(root, app_port)
            host = HostApp(manager, run_token="stage2-run-token", port=app_port).start()
            client = host.client(timeout=120.0)
            try:
                manifest = _install_enabled(manager, root, client)
                token = manager.runtime._handles[PLUGIN_ID].host_tool_token

                # 1. template
                status, template = host.host_tool(client, token, "training_config_template", {"pageTrainType": "sd-lora"}, session_id=SESSION)
                assert status == 200, template
                assert template["data"]["pageTrainType"] == "sd-lora"
                assert template["data"]["allowedFields"]

                # 2. draft in session workspace (relative paths, project-root cwd)
                draft = _make_draft_files(root)
                workspace.write_bytes("draft.toml", _draft_toml(draft).encode("utf-8"))

                # 3. validate (real schema + normalize + preflight chain)
                status, validated = host.host_tool(client, token, "training_config_validate", {"path": "draft.toml", "pageTrainType": "sd-lora"}, session_id=SESSION)
                assert status == 200, validated
                vdata = validated["data"]
                assert vdata["state"] == "preflight-pass"
                validation_hash = vdata["validationHash"]
                source_revision = vdata["sourceRevision"]

                # 4. commit without ticket -> confirmation required, zero canonical output.
                # The ticket is bound to this Tool call, so the approving call
                # must reuse the same tool_call_id.
                commit_call = "stage2-commit-call"
                status, pending = host.host_tool(client, token, "training_config_commit", {
                    "validationHash": validation_hash, "sourceRevision": source_revision, "confirmationTicketId": "",
                }, session_id=SESSION, tool_call_id=commit_call)
                assert status == 200, pending
                assert pending["data"]["state"] == "confirmation_required"
                ticket_id = pending["data"]["ticket"]["ticketId"]
                assert list((root / "config" / "autosave").glob("agent-*.toml")) == []

                # 5. host approves through the confirmation REST
                assert ticket_id == _resolve_pending(client, commit_call)

                # 6. commit with the approved ticket (same Tool call) -> canonical TOML
                status, committed = host.host_tool(client, token, "training_config_commit", {
                    "validationHash": validation_hash, "sourceRevision": source_revision, "confirmationTicketId": ticket_id,
                }, session_id=SESSION, tool_call_id=commit_call)
                assert status == 200, committed
                cdata = committed["data"]
                assert cdata["state"] == "committed"
                assert cdata["autoRun"] is False
                canonical = root / cdata["pathAlias"]
                assert canonical.is_file(), canonical
                loaded = toml.loads(canonical.read_text(encoding="utf-8"))
                assert loaded["model_train_type"] == "sd-lora"
                assert loaded["output_name"] == "stage2-agent-lora"

                # 7. fake trainer accepts the canonical TOML via the real import chain
                _fake_trainer(_write_fake_trainer(root), canonical)

                # 8. manual-import parity: same draft through the manual path equals the
                #    normalized config the artifact service committed
                imported = validate_config_import("sd-lora", dict(draft))
                assert imported["result"] == "ok", imported
                manual_normalized, _ = normalize_config_for_export(dict(imported["config"]), page_train_type="sd-lora")
                agent_normalized = get_artifact_service(SESSION)._validations[validation_hash]["normalized"]
                assert manual_normalized == agent_normalized

                # 9. negative gates
                # forged ticket
                status, err = host.host_tool(client, token, "training_config_commit", {
                    "validationHash": validation_hash, "sourceRevision": source_revision, "confirmationTicketId": "forged-" + uuid.uuid4().hex,
                }, session_id=SESSION, tool_call_id="stage2-forged")
                assert status == 404, err
                assert err["detail"]["code"] == "CONFIRMATION_NOT_FOUND"
                # wrong validation hash: the hash gate is enforced on the
                # approve-then-commit round trip (empty ticket creates the
                # pending ticket first, by design)
                wrong_hash = "wrong-" + uuid.uuid4().hex
                status, _ = host.host_tool(client, token, "training_config_commit", {
                    "validationHash": wrong_hash, "sourceRevision": source_revision, "confirmationTicketId": "",
                }, session_id=SESSION, tool_call_id="stage2-wronghash")
                assert status == 200
                wrong_ticket = _resolve_pending(client, "stage2-wronghash")
                status, err = host.host_tool(client, token, "training_config_commit", {
                    "validationHash": wrong_hash, "sourceRevision": source_revision, "confirmationTicketId": wrong_ticket,
                }, session_id=SESSION, tool_call_id="stage2-wronghash")
                assert status == 409, err
                assert err["detail"]["code"] == "CONFIG_CONFIRMATION_MISMATCH"
                # draft changed after validation
                workspace.write_bytes("draft.toml", _draft_toml({**draft, "output_name": "tampered"}).encode("utf-8"))
                status, _ = host.host_tool(client, token, "training_config_commit", {
                    "validationHash": validation_hash, "sourceRevision": source_revision, "confirmationTicketId": "",
                }, session_id=SESSION, tool_call_id="stage2-tampered")
                assert status == 200
                tampered_ticket = _resolve_pending(client, "stage2-tampered")
                status, err = host.host_tool(client, token, "training_config_commit", {
                    "validationHash": validation_hash, "sourceRevision": source_revision, "confirmationTicketId": tampered_ticket,
                }, session_id=SESSION, tool_call_id="stage2-tampered")
                assert status == 409, err
                assert err["detail"]["code"] == "CONFIG_SOURCE_CHANGED"
            finally:
                host.stop()
                client.close()
    finally:
        os.chdir(old_cwd)


def test_stage2_zero_short_fresh_path():
    require_dist()
    old_cwd = os.getcwd()
    try:
        with workspace_tempdir("stage2-zero-short-") as root:
            os.chdir(PROJECT_ROOT)
            zs_workspace = ensure_workspace("zs-session", purpose="training-config")
            _artifact_services["zs-session"] = TrainingConfigArtifactService(zs_workspace, project_root=root)
            app_port = free_port()
            manager = _manager(root, app_port)
            host = HostApp(manager, run_token="stage2-zs-run-token", port=app_port).start()
            client = host.client(timeout=120.0)
            try:
                manifest = _install_enabled(manager, root, client)
                token = manager.runtime._handles[PLUGIN_ID].host_tool_token

                # catalog: exactly the 13 contracted tools
                status, catalog = host.catalog(client, token)
                assert status == 200
                names = sorted(t["name"] for t in catalog["data"]["tools"])
                assert len(names) == 13, names
                assert "training_config_commit" in names and "training_config_template" in names

                # fresh-path journey: template -> draft -> validate -> approve -> commit
                status, template = host.host_tool(client, token, "training_config_template", {"pageTrainType": "sd-lora"}, session_id="zs-session")
                assert status == 200, template
                draft = _make_draft_files(root)
                zs_workspace.write_bytes("draft.toml", _draft_toml(draft).encode("utf-8"))
                status, validated = host.host_tool(client, token, "training_config_validate", {"path": "draft.toml", "pageTrainType": "sd-lora"}, session_id="zs-session")
                assert status == 200, validated
                vdata = validated["data"]
                zs_commit_call = "zs-commit-call"
                status, pending = host.host_tool(client, token, "training_config_commit", {
                    "validationHash": vdata["validationHash"], "sourceRevision": vdata["sourceRevision"], "confirmationTicketId": "",
                }, session_id="zs-session", tool_call_id=zs_commit_call)
                assert status == 200 and pending["data"]["state"] == "confirmation_required"
                ticket_id = _resolve_pending(client, zs_commit_call)
                status, committed = host.host_tool(client, token, "training_config_commit", {
                    "validationHash": vdata["validationHash"], "sourceRevision": vdata["sourceRevision"], "confirmationTicketId": ticket_id,
                }, session_id="zs-session", tool_call_id=zs_commit_call)
                assert status == 200, committed
                canonical = root / committed["data"]["pathAlias"]
                assert canonical.is_file()
                _fake_trainer(_write_fake_trainer(root), canonical)

                # disable + uninstall -> nothing left behind
                disabled = manager.disable(PLUGIN_ID)
                assert disabled.enabled is False and disabled.runtime_state == "stopped"
                manager.uninstall(PLUGIN_ID)
                assert manager.store.get_plugin(PLUGIN_ID) is None
            finally:
                host.stop()
                client.close()
    finally:
        os.chdir(old_cwd)

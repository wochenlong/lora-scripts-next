from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mikazuki.agent_workspace import AgentWorkspace, AgentDomainError, TrainingConfigArtifactService, redact
from mikazuki.agent_workspace.gateway import ToolRegistry, ToolMetadata


class AgentWorkspaceTests(unittest.TestCase):
    def test_workspace_manifest_and_relative_path_containment(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = AgentWorkspace(tmp, session_id="session-1")
            manifest = workspace.create()
            self.assertEqual(manifest.session_id, "session-1")
            workspace.write_text("training/draft.toml", "model_train_type = 'sd-lora'\n")
            self.assertEqual(workspace.read_text("training/draft.toml"), "model_train_type = 'sd-lora'\n")
            for path in ("../escape.toml", "C:/escape.toml", "//server/share/x.toml", "training/a:secret.toml"):
                with self.subTest(path=path), self.assertRaises(AgentDomainError) as raised:
                    workspace.resolve(path)
                self.assertIn(raised.exception.code, {"WORKSPACE_PATH_ESCAPE", "WORKSPACE_PATH_INVALID"})

    def test_workspace_rejects_unknown_extension_and_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = AgentWorkspace(tmp, session_id="s", max_file_bytes=4)
            workspace.create()
            with self.assertRaises(AgentDomainError) as raised:
                workspace.write_text("training/script.py", "x")
            self.assertEqual(raised.exception.code, "WORKSPACE_EXTENSION_FORBIDDEN")
            with self.assertRaises(AgentDomainError) as raised:
                workspace.write_text("training/draft.toml", "12345")
            self.assertEqual(raised.exception.code, "WORKSPACE_LIMIT_EXCEEDED")

    def test_redaction_only_exposes_configured(self):
        result = redact({"apiKey": "sk-super-secret-value", "nested": {"password": "pw", "value": "ok"}})
        self.assertEqual(result["apiKey"], "[configured]")
        self.assertEqual(result["nested"]["password"], "[configured]")
        self.assertEqual(result["nested"]["value"], "ok")


class TrainingConfigArtifactTests(unittest.TestCase):
    def test_validate_and_commit_reuses_import_path_and_never_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = AgentWorkspace(tmp, session_id="training")
            workspace.create()
            workspace.write_text("training/draft.json", json.dumps({"model_train_type": "sd-lora", "output_dir": "./out"}))
            service = TrainingConfigArtifactService(workspace, project_root=tmp)
            validation = service.validate_draft("training/draft.json", page_train_type="sd-lora")
            self.assertEqual(validation["state"], "preflight-pass")
            self.assertTrue(validation["validationHash"].startswith("sha256:"))
            committed = service.commit_draft(validation["validationHash"], confirmation_ticket={"state": "approved", "ticketId": "ticket-1"})
            self.assertEqual(committed["state"], "committed")
            self.assertFalse(committed["autoRun"])
            self.assertTrue((Path(tmp) / "config" / "autosave" / Path(committed["pathAlias"]).name).exists())

    def test_commit_requires_approved_ticket_and_detects_source_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = AgentWorkspace(tmp, session_id="training")
            workspace.create()
            workspace.write_text("draft.toml", "model_train_type = 'sd-lora'\n")
            service = TrainingConfigArtifactService(workspace, project_root=tmp)
            validation = service.validate_draft("draft.toml", page_train_type="sd-lora")
            with self.assertRaises(AgentDomainError) as raised:
                service.commit_draft(validation["validationHash"])
            self.assertEqual(raised.exception.code, "CONFIG_CONFIRMATION_REQUIRED")
            workspace.write_text("draft.toml", "model_train_type = 'sdxl-lora'\n")
            with self.assertRaises(AgentDomainError) as raised:
                service.commit_draft(validation["validationHash"], confirmation_ticket={"state": "approved"})
            self.assertEqual(raised.exception.code, "CONFIG_SOURCE_CHANGED")

    def test_sensitive_and_absolute_path_drafts_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = AgentWorkspace(tmp, session_id="training")
            workspace.create()
            service = TrainingConfigArtifactService(workspace)
            workspace.write_text("secret.json", json.dumps({"model_train_type": "sd-lora", "api_key": "x"}))
            with self.assertRaises(AgentDomainError) as raised:
                service.validate_draft("secret.json", page_train_type="sd-lora")
            self.assertEqual(raised.exception.code, "CONFIG_SENSITIVE_FIELD_REJECTED")
            workspace.write_text("absolute.json", json.dumps({"model_train_type": "sd-lora", "output_dir": "C:/tmp"}))
            with self.assertRaises(AgentDomainError) as raised:
                service.validate_draft("absolute.json", page_train_type="sd-lora")
            self.assertEqual(raised.exception.code, "CONFIG_PATH_UNBOUND")

    def test_nested_absolute_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = AgentWorkspace(tmp, session_id="training")
            workspace.create()
            service = TrainingConfigArtifactService(workspace)
            workspace.write_text(
                "nested.json",
                json.dumps({"model_train_type": "sd-lora", "dataset": [{"train_data_dir": "C:/outside"}]}),
            )
            with self.assertRaises(AgentDomainError) as raised:
                service.validate_draft("nested.json", page_train_type="sd-lora")
            self.assertEqual(raised.exception.code, "CONFIG_PATH_UNBOUND")


class ToolRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_tool_and_metadata_are_stable(self):
        registry = ToolRegistry()
        registry.register(ToolMetadata(name="workspace.read", purpose="Read a workspace file"), lambda envelope: {"value": "ok"})
        self.assertEqual(registry.metadata()[0]["name"], "workspace.read")
        result = await registry.invoke(registry.envelope("workspace.read", {}, session_id="s"))
        self.assertEqual(result, {"value": "ok"})
        with self.assertRaises(AgentDomainError) as raised:
            await registry.invoke(registry.envelope("unknown.read", {}, session_id="s"))
        self.assertEqual(raised.exception.code, "TOOL_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "cli"))
import install_musubi as cli  # noqa: E402

from mikazuki.engines.musubi.manifest import UPSTREAM  # noqa: E402


class InstallMusubiCliTests(unittest.TestCase):
    def test_dry_run_uses_manifest_pin_by_default(self):
        self._assert_dry_run_commit([], UPSTREAM["commit"])

    def test_dry_run_explicit_commit_overrides_manifest_pin(self):
        self._assert_dry_run_commit(["--source-commit", "deadbeef"], "deadbeef")

    def _assert_dry_run_commit(self, extra_args: list[str], expected_commit: str):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            source = project / "upstream"
            source.mkdir()
            captured: dict[str, object] = {}

            def resolve_source(project_root, explicit, source_commit):
                captured["resolve"] = (project_root, explicit, source_commit)
                return source

            def build_plan(project_root, layout, source_root, **kwargs):
                captured["plan"] = (project_root, layout, source_root, kwargs)
                return mock.Mock()

            with mock.patch.object(cli.os, "chdir"), mock.patch(
                "mikazuki.engines.musubi.settings.feature_enabled", return_value=True
            ), mock.patch(
                "mikazuki.engines.musubi.settings.resolve_install_source_root",
                side_effect=resolve_source,
            ), mock.patch(
                "mikazuki.engines.musubi.environment.resolve_cuda_extra",
                return_value="cu128",
            ), mock.patch(
                "mikazuki.engines.musubi.environment.build_environment_install_plan",
                side_effect=build_plan,
            ):
                rc = cli.main(["--project-root", str(project), "--dry-run", *extra_args])

            self.assertEqual(rc, 0)
            self.assertEqual(captured["resolve"][2], expected_commit)
            self.assertEqual(captured["plan"][3]["source_commit"], expected_commit)


if __name__ == "__main__":
    unittest.main()

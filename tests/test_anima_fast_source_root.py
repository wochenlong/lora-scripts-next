from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

_had_real_toml = "toml" in sys.modules
if not _had_real_toml:
    _fake_toml = types.ModuleType("toml")
    _fake_toml.loads = lambda _text: {}
    sys.modules["toml"] = _fake_toml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mikazuki.engines.anima_fast.source_root import (  # noqa: E402
    InstallSourceError,
    default_upstream_cache,
    resolve_install_source_root,
)

# Don't leak the fake toml into other test modules (it breaks real TOML
# parsing in e.g. task_insights tests); the imported module keeps its own ref.
if not _had_real_toml:
    sys.modules.pop("toml", None)


class AnimaFastSourceRootTests(unittest.TestCase):
    def _write_train_py(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        (path / "train.py").write_text("print('ok')\n", encoding="utf-8")

    def test_prefers_explicit_source_root(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "repo"
            project.mkdir()
            explicit = project / "upstream"
            self._write_train_py(explicit)
            resolved = resolve_install_source_root(project, explicit, None, allow_clone=False)
            self.assertEqual(resolved, explicit.resolve())

    def test_falls_back_to_cache_path_without_clone(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "repo"
            project.mkdir()
            with mock.patch(
                "mikazuki.engines.anima_fast.settings.discover_runtime",
                return_value=mock.Mock(anima_root=project / "missing", source_commit="abc123"),
            ):
                resolved = resolve_install_source_root(project, None, "abc123", allow_clone=False)
            self.assertEqual(resolved, default_upstream_cache(project))

    def test_uses_env_anima_lora_root(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "repo"
            project.mkdir()
            env_root = Path(td) / "env-anima"
            self._write_train_py(env_root)
            with mock.patch.dict(os.environ, {"ANIMA_LORA_ROOT": str(env_root)}):
                resolved = resolve_install_source_root(project, None, None, allow_clone=False)
            self.assertEqual(resolved, env_root.resolve())

    def test_clone_requires_git_when_no_source(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "repo"
            project.mkdir()
            with mock.patch(
                "mikazuki.engines.anima_fast.settings.discover_runtime",
                return_value=mock.Mock(anima_root=project / "missing", source_commit="abc123"),
            ), mock.patch("mikazuki.engines.anima_fast.source_root.shutil.which", return_value=None):
                with self.assertRaises(InstallSourceError):
                    resolve_install_source_root(project, None, "abc123", allow_clone=True)


if __name__ == "__main__":
    unittest.main()

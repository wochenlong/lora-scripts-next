from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mikazuki.anima_fast_backend.extension_state import ExtensionLayout
from mikazuki.anima_fast_backend.settings import discover_runtime


class AnimaFastSettingsTests(unittest.TestCase):
    def test_discover_runtime_prefers_linux_extension_venv_when_config_has_windows_path(self):
        with tempfile.TemporaryDirectory() as td, mock.patch(
            "mikazuki.anima_fast_backend.extension_state.sys.platform", "linux"
        ):
            root = Path(td)
            layout = ExtensionLayout(root / "extensions" / "anima_lora")
            layout.source.mkdir(parents=True)
            layout.train_py.write_text("", encoding="utf-8")
            layout.venv_python.parent.mkdir(parents=True)
            layout.venv_python.write_text("", encoding="utf-8")
            expected_python = layout.venv_python.resolve()
            external = root / "external_anima"
            external.mkdir()
            (external / "train.py").write_text("", encoding="utf-8")
            ext_py = external / ".venv" / "Scripts" / "python.exe"
            ext_py.parent.mkdir(parents=True)
            ext_py.write_text("", encoding="utf-8")
            config_path = root / "config" / "anima_fast_backend.toml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                "\n".join(
                    [
                        "[backend]",
                        'source_dir = "extensions/anima_lora/source"',
                        'venv_python = "extensions/anima_lora/.venv/Scripts/python.exe"',
                        f'external_root = "{external.as_posix()}"',
                        f'external_python = "{ext_py.as_posix()}"',
                    ]
                ),
                encoding="utf-8",
            )
            runtime = discover_runtime(lora_next_root=root)

        self.assertEqual(runtime.python.resolve(), expected_python)

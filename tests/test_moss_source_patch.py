import hashlib
import subprocess
from pathlib import Path

import pytest

from mikazuki.engines.moss import environment, installer, source_integrity
from mikazuki.engines.moss.settings import Runtime
from mikazuki.download_sources import DownloadSources


@pytest.fixture
def source(tmp_path, monkeypatch):
    root = tmp_path / 'source with spaces'
    root.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()
    git('init', '-q')
    (root / 'module.py').write_text('value = 1\n')
    git('add', 'module.py')
    git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture')
    patch = tmp_path / 'source patch.diff'
    patch.write_text('--- a/module.py\n+++ b/module.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n')
    monkeypatch.setattr(source_integrity, 'UPSTREAM', {'commit': git('rev-parse', 'HEAD')})
    monkeypatch.setattr(source_integrity, 'PATCH_FILE', patch)
    monkeypatch.setattr(source_integrity, 'PATCHED_FILES', {'module.py': hashlib.sha256(b'value = 2\n').hexdigest()})
    return root


def test_source_patch_applies_once_and_rejects_drift(source):
    source_integrity.apply_source_patch(source)
    source_integrity.apply_source_patch(source)
    assert (source / 'module.py').read_text() == 'value = 2\n'
    (source / 'unrelated.py').write_text('value = 3\n')
    with pytest.raises(ValueError, match='modified|drift'):
        source_integrity.apply_source_patch(source)


def test_source_patch_rejects_wrong_contents_and_commit(source, monkeypatch):
    (source / 'module.py').write_text('value = 9\n')
    with pytest.raises(ValueError, match='fingerprint'):
        source_integrity.verify_source(type('Runtime', (), {'source': source})())
    monkeypatch.setattr(source_integrity, 'UPSTREAM', {'commit': '0' * 40})
    with pytest.raises(ValueError, match='commit'):
        source_integrity.apply_source_patch(source)


def test_windows_install_plan_cleans_conflicting_uv_preference(tmp_path, monkeypatch):
    monkeypatch.setattr(environment.sys, 'platform', 'win32')
    monkeypatch.setattr(environment.platform, 'machine', lambda: 'AMD64')
    monkeypatch.setenv('UV_PYTHON_PREFERENCE', 'only-system')
    monkeypatch.setenv('PYTHONPATH', 'unrelated modules')
    rt = Runtime(tmp_path / 'trainer with spaces')
    env = environment.install_env(rt)
    assert 'UV_PYTHON_PREFERENCE' not in env and 'PYTHONPATH' not in env
    assert env['UV_PYTHON_INSTALL_DIR'] == str(rt.python_install_dir)
    commands = installer.installation_plan(rt, DownloadSources())
    assert any('mikazuki.engines.moss.source_integrity' in command for command in commands)
    venv = next(command for command in commands if command[:2] == ['uv', 'venv'])
    assert '--managed-python' in venv
    assert venv[-1] == str(rt.root / '.venv')
    assert any(str(rt.python) in command for command in commands if command[:3] == ['uv', 'pip', 'install'])
    assert str(rt.python).replace('\\', '/').endswith('Scripts/python.exe')

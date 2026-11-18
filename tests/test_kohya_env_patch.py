"""A kohya main-env upgrade writes config/kohya_env_patch.json; while present
for the running interpreter, the GUI launcher skips the requirements version
sync entirely so upgraded training pins are never rolled back."""
import json
import sys

import pytest

from mikazuki import launch_utils


@pytest.fixture
def patch_env(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    monkeypatch.setattr(launch_utils, "base_dir_path", lambda: tmp_path)
    return config / "kohya_env_patch.json"


def write_patch(path, packages=None, python=None):
    path.write_text(json.dumps({
        "python": python if python is not None else sys.executable,
        "packages": packages if packages is not None else {"huggingface-hub": "==1.32.0"},
    }), encoding="utf-8")


def test_patch_skips_version_sync(patch_env, monkeypatch, tmp_path):
    write_patch(patch_env)
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("huggingface-hub==0.36.2\n", encoding="utf-8")

    monkeypatch.setattr(launch_utils, "run_pip", lambda *a, **kw: pytest.fail("pip must not run"))
    monkeypatch.setattr(launch_utils, "is_installed", lambda spec: False)

    launch_utils.validate_requirements(str(requirements))


def test_without_patch_wrong_version_triggers_install(patch_env, monkeypatch, tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("huggingface-hub==0.36.2\n", encoding="utf-8")

    pip_calls = []
    monkeypatch.setattr(launch_utils, "run_pip", lambda *a, **kw: pip_calls.append(a))
    monkeypatch.setattr(launch_utils, "is_installed", lambda spec: False)

    launch_utils.validate_requirements(str(requirements))

    assert len(pip_calls) == 1
    assert "huggingface-hub==0.36.2" in pip_calls[0][0]


def test_patch_ignored_for_other_interpreter(patch_env, tmp_path):
    write_patch(patch_env, python=str(tmp_path / "other" / "python"))
    assert launch_utils.env_patch_active() is False


def test_patch_missing_or_malformed_is_inert(patch_env):
    assert launch_utils.env_patch_active() is False
    patch_env.write_text("not json", encoding="utf-8")
    assert launch_utils.env_patch_active() is False
    write_patch(patch_env, packages={})
    assert launch_utils.env_patch_active() is False

import json
from pathlib import Path
import runpy

import pytest

ROOT = Path(__file__).resolve().parents[1]


def runtime():
    path = ROOT / "mikazuki/engines/anima_fast/portable_runtime.py"
    assert path.is_file(), "portable relocation support missing"
    return runpy.run_path(str(path))


def fixture(root):
    (root / ".python").mkdir(parents=True)
    (root / ".python/python.exe").touch()
    (root / ".venv").mkdir()
    (root / ".venv/pyvenv.cfg").write_text(
        "home = C:\\outside\\Python\ninclude-system-site-packages = false\n"
        "version = 3.13.9\nexecutable = C:\\outside\\Python\\python.exe\n")
    (root / "portable-runtime.json").write_text(json.dumps({"version": 1}))


def test_relocate_repairs_only_marked_runtime(tmp_path):
    fixture(tmp_path)
    runtime()["repair"](tmp_path)
    text = (tmp_path / ".venv/pyvenv.cfg").read_text()
    assert str(tmp_path / ".python") in text
    assert "outside" not in text
    assert "include-system-site-packages = false" in text
    moved = tmp_path.parent / (tmp_path.name + " moved")
    tmp_path.rename(moved)
    runtime()["repair"](moved)
    assert str(moved / ".python") in (moved / ".venv/pyvenv.cfg").read_text()


def test_unmarked_developer_environment_is_untouched(tmp_path):
    fixture(tmp_path)
    (tmp_path / "portable-runtime.json").unlink()
    before = (tmp_path / ".venv/pyvenv.cfg").read_bytes()
    runtime()["repair"](tmp_path)
    assert (tmp_path / ".venv/pyvenv.cfg").read_bytes() == before


def test_missing_bundled_base_fails_without_rewriting(tmp_path):
    fixture(tmp_path)
    (tmp_path / ".python/python.exe").unlink()
    before = (tmp_path / ".venv/pyvenv.cfg").read_bytes()
    with pytest.raises(RuntimeError, match="base Python"):
        runtime()["repair"](tmp_path)
    assert (tmp_path / ".venv/pyvenv.cfg").read_bytes() == before


def test_fast_profile_launcher_does_not_require_host_torch():
    text = (ROOT / "scripts/portable/launch_portable.bat").read_text(encoding="utf-8")
    assert 'portable-profile.json" goto :fast_profile' in text
    profile = text.split(":fast_profile\n")[-1].split(":first_run")[0]
    assert "verify_fast_package.py" in profile
    assert "goto :launch" in profile
    assert "setup_environment.py" not in profile


def test_fast_builder_installs_gui_after_temporary_cleanup():
    text = (ROOT / "build-scripts/build_portable.ps1").read_text(encoding="utf-8-sig")
    assert "bundle_fast_runtime.py" in text
    install = text.index("# Complete Fast host")
    assert install > text.index("Cleared build-time pip packages")
    assert "verify_fast_package.py" in text[install:]
    assert "portable-profile.json" in text[install:]


def test_verifier_rejects_external_runtime_paths(tmp_path):
    path = ROOT / "scripts/portable/verify_fast_package.py"
    checker = runpy.run_path(str(path))["require_inside"]
    checker(tmp_path / "python.exe", tmp_path)
    with pytest.raises(RuntimeError, match="escapes"):
        checker(tmp_path.parent / "external/python.exe", tmp_path)


def test_main_audit_does_not_import_training_torch(monkeypatch):
    import builtins
    from mikazuki.engines.anima_fast.environment import _main_facts_in_process
    original = builtins.__import__
    calls = []

    def importing(name, *args, **kwargs):
        if name == "torch":
            calls.append(name)
            raise ImportError("GUI intentionally has no torch")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", importing)
    facts = _main_facts_in_process()
    assert calls == []
    assert "torch" not in facts["imports"]


def test_fast_builder_skips_unrelated_tokenizer_downloads():
    text = (ROOT / "build-scripts/build_portable.ps1").read_text(encoding="utf-8-sig")
    assert "if (-not $BundleAnimaFast) {\n# SD-family tokenizer prefetch" in text


def test_gui_without_transformers_does_not_partially_patch_modelscope(monkeypatch):
    import builtins
    import sys
    from types import SimpleNamespace
    from unittest.mock import Mock
    import mikazuki.china_hub as hub

    original = builtins.__import__

    def importing(name, *args, **kwargs):
        if name == "transformers" or name.startswith("transformers."):
            raise ImportError("GUI-only environment")
        return original(name, *args, **kwargs)

    patch = Mock(side_effect=ImportError("transformers missing inside patch_hub"))
    aliases = Mock()
    monkeypatch.setitem(sys.modules, "modelscope.utils.hf_util", SimpleNamespace(patch_hub=patch))
    monkeypatch.setattr(builtins, "__import__", importing)
    monkeypatch.setattr(hub, "_PATCHED", False)
    monkeypatch.setattr(hub, "_patch_modelscope_download_aliases", aliases)
    assert hub.enable_china_hub(force=True) is False
    patch.assert_not_called()
    aliases.assert_not_called()


def test_gui_only_verification_does_not_probe_uninstalled_fast(tmp_path, monkeypatch):
    from types import SimpleNamespace
    checker = runpy.run_path(str(ROOT / "scripts/portable/verify_fast_package.py"))
    (tmp_path / "portable-profile.json").write_text('{"version":1,"profile":"gui-fast"}')
    monkeypatch.setattr(checker["sys"], "executable", str(tmp_path / "python.exe"))
    monkeypatch.setattr(checker["sys"], "prefix", str(tmp_path))
    monkeypatch.setattr(checker["sys"], "base_prefix", str(tmp_path))
    monkeypatch.setattr(checker["importlib"], "import_module",
                        lambda name: SimpleNamespace(__file__=str(tmp_path / name / "__init__.py")))
    def unexpected(*args, **kwargs):
        pytest.fail("GUI startup must not probe the Fast runtime")
    monkeypatch.setattr(checker["subprocess"], "run", unexpected)
    checker["verify"](tmp_path, gui_only=True)
    with pytest.raises((FileNotFoundError, RuntimeError)):
        checker["verify"](tmp_path)


def test_launcher_uses_gui_only_check():
    text = (ROOT / "scripts/portable/launch_portable.bat").read_text(encoding="utf-8")
    line = next(line for line in text.splitlines() if '" -s ' in line and "verify_fast_package.py" in line)
    assert "--gui-only" in line


@pytest.mark.parametrize("damage", ["base", "config", "marker"])
def test_broken_portable_status_is_structured_and_path_is_readable(tmp_path, damage):
    from mikazuki.engines.anima_fast.extension_state import ExtensionLayout, read_extension_status
    fixture(tmp_path)
    if damage == "base":
        (tmp_path / ".python/python.exe").unlink()
    elif damage == "config":
        (tmp_path / ".venv/pyvenv.cfg").unlink()
    else:
        (tmp_path / "portable-runtime.json").write_text("{")
    layout = ExtensionLayout(tmp_path)
    assert layout.venv_python == tmp_path / ".venv/Scripts/python.exe"
    status = read_extension_status(layout)
    assert status.state == "broken"
    assert "portable" in status.reason.lower()


def test_rebuild_portable_base_preserves_packages_and_relocation(tmp_path):
    fixture(tmp_path / "extension")
    root = tmp_path / "extension"
    (root / ".python/python.exe").unlink()
    site = root / ".venv/Lib/site-packages"
    site.mkdir(parents=True)
    (site / "keep.py").write_text("data")
    downloaded = tmp_path / "downloaded"
    downloaded.mkdir()
    (downloaded / "python.exe").write_text("new interpreter")
    (downloaded / "Lib/site-packages").mkdir(parents=True)
    (downloaded / "Lib/site-packages/private.py").touch()
    result = runtime()["rebuild_base"](root, downloaded / "python.exe")
    assert result == root / ".python/python.exe"
    assert result.read_text() == "new interpreter"
    assert not (root / ".python/Lib/site-packages").exists()
    assert (site / "keep.py").read_text() == "data"
    runtime()["repair"](root)


def test_broken_runtime_audit_fails_without_running_engine(tmp_path, monkeypatch):
    from mikazuki.engines.anima_fast import environment
    from mikazuki.engines.anima_fast.extension_state import ExtensionLayout
    fixture(tmp_path)
    (tmp_path / ".python/python.exe").unlink()
    def unexpected(*args, **kwargs):
        pytest.fail("A broken portable base must not be executed")
    monkeypatch.setattr(environment, "_collect_python_facts", unexpected)
    result = environment.audit_environment(tmp_path, ExtensionLayout(tmp_path))
    assert not result.ok
    assert "Portable" in result.errors[0]


def test_repair_route_can_schedule_broken_portable_runtime(tmp_path, monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from mikazuki.engines.anima_fast import routes
    from mikazuki.engines.anima_fast.extension_state import ExtensionLayout
    fixture(tmp_path)
    (tmp_path / ".python/python.exe").unlink()
    layout = ExtensionLayout(tmp_path)
    monkeypatch.setattr(routes, "default_layout", lambda root: layout)
    monkeypatch.setattr(routes, "feature_enabled", lambda: True)
    monkeypatch.setattr(routes, "anima_fast_runtime", lambda: SimpleNamespace(source_commit="abc"))
    monkeypatch.setattr(routes, "resolve_install_source_root", lambda *a, **kw: tmp_path)
    scheduled = []
    def schedule(*args, **kwargs):
        scheduled.append(args)
        return "test-repair", {}
    monkeypatch.setattr(routes, "start_install_task", schedule)
    asyncio.run(routes.repair({"dry_run": False}))
    assert len(scheduled) == 1


def test_rebuild_rejects_linked_venv_config_before_writes(tmp_path, monkeypatch):
    root = tmp_path / "extension"
    fixture(root)
    external = tmp_path / "external.cfg"
    external.write_text("preserve")
    config = root / ".venv/pyvenv.cfg"
    config.unlink()
    try:
        config.symlink_to(external)
    except OSError:
        config.touch()
        original_resolve = Path.resolve
        monkeypatch.setattr(Path, "resolve", lambda path, *a, **kw:
                            external if path == config else original_resolve(path, *a, **kw))
    downloaded = tmp_path / "base"
    downloaded.mkdir()
    (downloaded / "python.exe").write_text("base")
    with pytest.raises(RuntimeError, match="linked|outside"):
        runtime()["rebuild_base"](root, downloaded / "python.exe")
    assert external.read_text() == "preserve"


def test_active_repair_state_survives_missing_portable_base(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from mikazuki.tasks import TaskStatus, tm
    from mikazuki.engines.anima_fast.extension_state import (
        ExtensionLayout, read_extension_status, write_install_state,
    )
    fixture(tmp_path)
    (tmp_path / ".python/python.exe").unlink()
    layout = ExtensionLayout(tmp_path)
    write_install_state(layout, "installing", {"task_id": "repair-active"})
    monkeypatch.setitem(tm.tasks, "repair-active", SimpleNamespace(status=TaskStatus.RUNNING))
    status = read_extension_status(layout)
    assert status.state == "installing"
    assert status.facts["task_id"] == "repair-active"

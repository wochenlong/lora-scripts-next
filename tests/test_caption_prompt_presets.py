import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from mikazuki.llm.prompt_presets import list_presets, save_presets, save_settings, settings, save_document, document_revision
from mikazuki.llm.config import LLMContractError


def _preset(identifier="caption-zh"):
    return {
        "id": identifier,
        "kind": "caption_prompt",
        "name": "中文描述",
        "template": "请用{{language}}描述可见事实。",
        "system_prompt": "不要臆测。",
        "output_format": "plain_text",
        "language": "zh-CN",
        "max_length": 240,
        "model_capabilities": ["vision", "caption"],
    }


def test_caption_presets_are_stored_as_typed_user_data(monkeypatch, tmp_path):
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path / "user_data"))
    saved = save_presets([_preset()])
    assert saved[0]["kind"] == "caption_prompt"
    assert saved[0]["revision"]
    assert list_presets()[0]["id"] == "caption-zh"
    assert json.loads((tmp_path / "user_data" / "presets" / "caption-zh.json").read_text(encoding="utf-8"))["kind"] == "caption_prompt"


def test_caption_preset_settings_reference_existing_preset(monkeypatch, tmp_path):
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path / "user_data"))
    save_presets([_preset()])
    assert save_settings("caption-zh")["default_caption_preset_id"] == "caption-zh"
    assert settings()["default_caption_preset_id"] == "caption-zh"


def test_caption_preset_rejects_training_kind_and_unknown_variable(monkeypatch, tmp_path):
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path / "user_data"))
    with pytest.raises(LLMContractError):
        save_presets([{**_preset(), "kind": "training"}])
    with pytest.raises(LLMContractError):
        save_presets([{**_preset(), "template": "{{secret}}"}])


def test_caption_preset_save_removes_deleted_caption_files(monkeypatch, tmp_path):
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path / "user_data"))
    save_presets([_preset(), _preset("caption-en")])
    save_presets([_preset()])
    assert [item["id"] for item in list_presets()] == ["caption-zh"]


def test_caption_save_preserves_training_presets_and_unrelated_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path))
    directory = tmp_path / "presets"
    directory.mkdir()
    training = directory / "train.json"
    training.write_text('{"kind":"training","name":"keep"}', encoding="utf-8")
    settings_file = tmp_path / "settings.json"
    settings_file.write_text('{"theme":"dark","gui_port":6006}', encoding="utf-8")
    before = training.read_bytes()
    save_document({"presets": [_preset()], "settings": {"default_caption_preset_id": "caption-zh"}, "revision": document_revision()})
    assert training.read_bytes() == before
    assert json.loads(settings_file.read_text(encoding="utf-8"))["gui_port"] == 6006
    assert json.loads(settings_file.with_suffix(".json.bak").read_text(encoding="utf-8"))["theme"] == "dark"


def test_foreign_id_collision_and_stale_revision_do_not_mutate(monkeypatch, tmp_path):
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path))
    (tmp_path / "presets").mkdir()
    foreign = tmp_path / "presets" / "caption-zh.json"
    foreign.write_text('{"kind":"training"}', encoding="utf-8")
    with pytest.raises(LLMContractError, match="collides"):
        save_presets([_preset()])
    assert foreign.read_text(encoding="utf-8") == '{"kind":"training"}'
    revision = document_revision()
    save_presets([_preset("new")])
    with pytest.raises(LLMContractError, match="revision conflict"):
        save_document({"presets": [], "revision": revision})
    assert list_presets()[0]["id"] == "new"


def test_invalid_default_reference_is_rejected_before_write(monkeypatch, tmp_path):
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path))
    with pytest.raises(LLMContractError):
        save_document({"presets": [_preset()], "settings": {"default_caption_preset_id": "missing"}, "revision": document_revision()})
    assert not (tmp_path / "presets").exists()


def test_explicit_legacy_import_preserves_current_user_version(monkeypatch, tmp_path):
    from mikazuki.llm.prompt_presets import import_legacy
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path))
    save_presets([_preset()])
    legacy = {"id": "caption-zh", "name": "旧版本", "template": "旧提示词", "language": "en"}
    imported = import_legacy([legacy, {**legacy, "id": "legacy-en"}], expected_revision=document_revision())
    assert len(imported["presets"]) == 2
    assert next(item for item in list_presets() if item["id"] == "caption-zh")["name"] == "中文描述"
    assert imported["settings"]["legacy_imported"] is True
    again = import_legacy([{**legacy, "id": "not-imported-twice"}], expected_revision=imported["revision"])
    assert again == imported


def test_preset_http_conflict_and_import_confirmation(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from mikazuki.llm.api import router
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path))
    app = FastAPI()
    app.include_router(router, prefix="/api")
    with TestClient(app) as client:
        document = client.get("/api/llm/prompt-presets").json()["data"]
        assert document["presets"] == []
        response = client.put("/api/llm/prompt-presets", json={**document, "presets": [_preset()]})
        assert response.status_code == 200
        assert client.put("/api/llm/prompt-presets", json=document).status_code == 409
        assert client.post("/api/llm/prompt-presets/import-legacy", json={"confirmed": False}).status_code == 400


def test_failed_multi_file_save_restores_presets_settings_and_backups(monkeypatch, tmp_path):
    from mikazuki.llm import prompt_presets as store
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path))
    original = save_document({"presets": [_preset()], "settings": {"default_caption_preset_id": "caption-zh"}, "revision": document_revision()})
    original = save_document({**original, "presets": [{**_preset(), "name": "第二版"}]})
    before = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file() and path.name != ".caption-presets.lock"}
    replace = store.os.replace
    rejected = []

    def fail_settings_once(source, destination):
        if Path(destination) == tmp_path / "settings.json" and not rejected:
            rejected.append(True)
            raise OSError("injected disk error")
        return replace(source, destination)

    monkeypatch.setattr(store.os, "replace", fail_settings_once)
    with pytest.raises(OSError):
        save_document({"presets": [_preset("new")], "settings": {"default_caption_preset_id": "new"}, "revision": original["revision"]})
    after = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file() and path.name != ".caption-presets.lock"}
    assert after == before
    assert store.document()["revision"] == original["revision"]


@pytest.mark.parametrize("exit_stage", ["applying", "committed"])
def test_abrupt_process_exit_recovers_a_whole_document(monkeypatch, tmp_path, exit_stage):
    from mikazuki.llm import prompt_presets as store
    root = tmp_path / "user_data"
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(root))
    original = save_document({"presets": [_preset()], "settings": {"default_caption_preset_id": "caption-zh"}, "revision": document_revision()})
    script = r'''
import json, os, sys
from pathlib import Path
from mikazuki.llm import prompt_presets as store
current = store.document()
preset = {**current["presets"][0], "id": "new", "name": "New"}
write = store._atomic_bytes
def interrupted(target, value):
    write(target, value)
    if sys.argv[1] == "applying" and target.name == "new.json":
        os._exit(91)
    if sys.argv[1] == "committed" and target.name == store._JOURNAL and json.loads(value)["state"] == "committed":
        os._exit(91)
store._atomic_bytes = interrupted
store.save_document({"presets":[preset], "settings":{"default_caption_preset_id":"new"}, "revision":current["revision"]})
'''
    result = subprocess.run([sys.executable, "-c", script, exit_stage], cwd=Path(__file__).resolve().parents[1], env=os.environ.copy(), capture_output=True, timeout=15)
    assert result.returncode == 91, result.stderr.decode(errors="replace")
    assert (root / store._JOURNAL).is_file()
    restored = store.document()
    if exit_stage == "applying":
        assert restored == original
        assert not (root / "presets" / "new.json").exists()
    else:
        assert [item["id"] for item in restored["presets"]] == ["new"]
        assert restored["settings"]["default_caption_preset_id"] == "new"
    assert not (root / store._JOURNAL).exists()


def test_two_independent_writers_cannot_overwrite_the_same_revision(monkeypatch, tmp_path):
    from mikazuki.llm import prompt_presets as store
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path / "user_data"))
    save_document({"presets": [_preset()], "settings": {}, "revision": document_revision()})
    script = r'''
import sys, time
from pathlib import Path
from mikazuki.llm import prompt_presets as store
from mikazuki.llm.config import LLMContractError
current = store.document()
Path(sys.argv[1]).write_text("ready")
deadline = time.monotonic() + 10
while not Path(sys.argv[2]).exists():
    if time.monotonic() > deadline: raise RuntimeError("barrier timed out")
    time.sleep(.01)
current["presets"][0]["name"] = sys.argv[3]
try:
    store.save_document(current)
    print("saved", flush=True)
except LLMContractError as error:
    if "revision conflict" not in str(error): raise
    print("conflict", flush=True)
'''
    processes = []
    try:
        for number in range(2):
            processes.append(subprocess.Popen([sys.executable, "-c", script, str(tmp_path / f"ready-{number}"), str(tmp_path / "go"), f"writer-{number}"], cwd=Path(__file__).resolve().parents[1], env=os.environ.copy(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        deadline = time.monotonic() + 10
        while not all((tmp_path / f"ready-{number}").exists() for number in range(2)):
            assert time.monotonic() < deadline, "writers did not reach barrier"
            time.sleep(.01)
        (tmp_path / "go").write_text("go")
        results = [process.communicate(timeout=10) for process in processes]
        assert [process.returncode for process in processes] == [0, 0], results
        assert sorted(output.strip() for output, _error in results) == ["conflict", "saved"]
        assert store.document()["presets"][0]["name"] in {"writer-0", "writer-1"}
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)


def test_unrelated_settings_edit_invalidates_caption_revision(monkeypatch, tmp_path):
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path))
    revision = document_revision()
    (tmp_path / "settings.json").write_text('{"theme":"dark"}', encoding="utf-8")
    with pytest.raises(LLMContractError, match="revision conflict"):
        save_document({"presets": [_preset()], "settings": {}, "revision": revision})
    assert not (tmp_path / "presets").exists()


def test_preset_directory_cannot_redirect_writes_outside_user_data(monkeypatch, tmp_path):
    from mikazuki.llm.prompt_presets import document
    root, external = tmp_path / "user_data", tmp_path / "external"
    root.mkdir()
    external.mkdir()
    marker = external / "training.json"
    marker.write_bytes(b'{"kind":"training"}')
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(root))
    if os.name == "nt":
        result = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(root / "presets"), str(external)], capture_output=True, timeout=5)
        assert result.returncode == 0, result.stderr.decode(errors="replace")
    else:
        (root / "presets").symlink_to(external, target_is_directory=True)
    with pytest.raises(LLMContractError):
        document()
    with pytest.raises(LLMContractError):
        save_presets([_preset()])
    assert marker.read_bytes() == b'{"kind":"training"}'
    assert not (external / "caption-zh.json").exists()


def test_recovery_rejects_paths_outside_caption_storage(monkeypatch, tmp_path):
    from mikazuki.llm import prompt_presets as store
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path))
    (tmp_path / "auth.json").write_bytes(b'{"keep":true}')
    (tmp_path / store._JOURNAL).write_text(json.dumps({"schema_version": 1, "state": "prepared", "files": [{"path": "auth.json", "before": None, "after": None}]}), encoding="utf-8")
    with pytest.raises(LLMContractError, match="transaction path"):
        store.document()
    assert (tmp_path / "auth.json").read_bytes() == b'{"keep":true}'

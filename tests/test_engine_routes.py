"""Generic /api/engines/* router: kind-based lifecycle gating and import errors."""

import asyncio
import json
import sys
import types

from starlette.requests import Request

from mikazuki.app import api
from mikazuki.engines import registry
from mikazuki.engines.manifest import KIND_BUILTIN, KIND_PLUGIN, load_manifest
from mikazuki.engines.registry import EnginePack


def make_request(payload: dict) -> Request:
    body = json.dumps(payload).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": "POST", "path": "/api/test", "headers": []}, receive)


def _make_pack(monkeypatch, engine_id: str, kind: str, with_routes: bool = True, with_install: bool = True) -> EnginePack:
    package = f"mikazuki.engines.{engine_id.replace('-', '_')}_testpack"
    manifest_mod = types.ModuleType(f"{package}.manifest")
    manifest_mod.ENGINE_ID = engine_id
    manifest_mod.KIND = kind
    manifest_mod.TRAIN_TYPES = {f"{engine_id}-lora": "v"}
    manifest_mod.UPSTREAM = {"repo": "example/x", "commit": "abc123", "zip": None, "github": "https://github.com/example/x.git", "gitee": None}
    manifest_mod.FEATURE_FLAG_ENV = ""
    monkeypatch.setitem(sys.modules, package, types.ModuleType(package))
    monkeypatch.setitem(sys.modules, f"{package}.manifest", manifest_mod)
    if with_routes:
        routes_mod = types.ModuleType(f"{package}.routes")
        if with_install:
            async def install(payload, force_install=False):
                return api.APIResponseSuccess(data={"installed": True, "force": force_install})

            routes_mod.install = install
        monkeypatch.setitem(sys.modules, f"{package}.routes", routes_mod)
    pack = EnginePack(manifest=load_manifest(manifest_mod), package=package)
    real_packs = registry.discover_packs()
    monkeypatch.setattr(registry, "discover_packs", lambda: {**real_packs, engine_id: pack})
    return pack


def test_builtin_pack_rejects_install_even_with_handler(monkeypatch):
    _make_pack(monkeypatch, "fakebuiltin", KIND_BUILTIN, with_routes=True)
    response = asyncio.run(api.engine_install("fakebuiltin", make_request({})))
    assert response.status == "fail"
    assert "内置引擎" in response.message


def test_builtin_pack_rejects_uninstall(monkeypatch):
    _make_pack(monkeypatch, "fakebuiltin", KIND_BUILTIN, with_routes=True)
    response = asyncio.run(api.engine_uninstall("fakebuiltin"))
    assert response.status == "fail"
    assert "不可卸载" in response.message


def test_plugin_without_install_handler_gets_clear_error(monkeypatch):
    _make_pack(monkeypatch, "fakeplugin", KIND_PLUGIN, with_routes=True, with_install=False)
    response = asyncio.run(api.engine_install("fakeplugin", make_request({})))
    assert response.status == "fail"
    assert "未提供安装接口" in response.message


def test_plugin_install_dispatches_normally(monkeypatch):
    _make_pack(monkeypatch, "fakeplugin", KIND_PLUGIN, with_routes=True)
    response = asyncio.run(api.engine_install("fakeplugin", make_request({})))
    assert response.status == "success"
    assert response.data["installed"] is True


def test_missing_routes_module_is_404(monkeypatch):
    _make_pack(monkeypatch, "noroutes", KIND_PLUGIN, with_routes=False)
    try:
        api._engine_routes_module("noroutes")
        raise AssertionError("expected HTTPException")
    except api.HTTPException as exc:
        assert exc.status_code == 404


def test_nested_import_error_is_not_masked_as_404(monkeypatch):
    _make_pack(monkeypatch, "brokenpack", KIND_PLUGIN, with_routes=False)

    def boom(self, name):
        raise ModuleNotFoundError("No module named 'some_missing_dep'", name="some_missing_dep")

    monkeypatch.setattr(EnginePack, "import_module", boom)
    try:
        api._engine_routes_module("brokenpack")
        raise AssertionError("expected ModuleNotFoundError to propagate")
    except ModuleNotFoundError as exc:
        assert exc.name == "some_missing_dep"
    except api.HTTPException:
        raise AssertionError("nested import failure must not be masked as 404")

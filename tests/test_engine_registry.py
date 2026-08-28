"""Registry discovery: both migrated packs are found and train_types map."""

import sys
import types

from mikazuki.engines import registry
from mikazuki.engines.manifest import KIND_BUILTIN, KIND_PLUGIN
from mikazuki.engines.runner import RunContext, dispatch_run


def test_discovers_migrated_packs():
    packs = registry.discover_packs()
    assert set(packs) == {"musubi", "anima-fast", "kohya", "ai-toolkit"}
    assert packs["kohya"].manifest.kind == KIND_BUILTIN
    for engine_id in ("musubi", "anima-fast", "ai-toolkit"):
        pack = packs[engine_id]
        assert pack.manifest.kind == KIND_PLUGIN
        assert pack.manifest.upstream["repo"]
        assert "github" in pack.manifest.upstream
        assert "gitee" in pack.manifest.upstream
        assert "zip" in pack.manifest.upstream


def test_train_type_mapping():
    mapping = registry.train_type_map()
    assert mapping["krea2-lora"] == ("musubi", "krea2")
    assert mapping["anima-lora-fast"] == ("anima-fast", "anima")
    assert mapping["sd-lora"] == ("kohya", "sd15")
    assert mapping["flux-finetune"] == ("kohya", "flux")
    assert mapping["lumina-lora"] == ("kohya", "lumina")
    assert mapping["klein-4b-lora"] == ("ai-toolkit", "klein-4b")
    assert mapping["klein-9b-lora"] == ("ai-toolkit", "klein-9b")


def test_resolve_train_type_roundtrip():
    pack, variant = registry.resolve_train_type("krea2-lora")
    assert pack.engine_id == "musubi"
    assert variant == "krea2"
    assert registry.resolve_train_type("no-such-type") is None


def test_pack_modules_importable():
    pack = registry.get_pack("musubi")
    adapter = pack.import_module("adapter")
    assert adapter is not None


def test_template_dir_is_not_registered():
    assert "_template" not in registry.discover_packs()
    assert "your-engine" not in registry.discover_packs()


def test_template_manifest_is_valid():
    import importlib.util
    from pathlib import Path

    from mikazuki.engines.manifest import load_manifest

    spec = importlib.util.spec_from_file_location(
        "_template_manifest", Path("mikazuki/engines/_template/manifest.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = load_manifest(module)
    assert manifest.engine_id == "your-engine"


def test_virtual_pack_dispatches_without_api_changes(monkeypatch):
    """Core criterion: a hypothetical pack (manifest + empty suite) is dispatched
    by /api/run's dispatch path with zero changes outside its own directory."""
    package = "mikazuki.engines.hypo"
    manifest_mod = types.ModuleType(f"{package}.manifest")
    manifest_mod.ENGINE_ID = "hypo"
    manifest_mod.KIND = KIND_PLUGIN
    manifest_mod.TRAIN_TYPES = {"hypo-lora": "hypo"}
    manifest_mod.UPSTREAM = {"repo": "example/hypo", "commit": "abc123", "zip": None, "github": "https://github.com/example/hypo.git", "gitee": None}
    manifest_mod.FEATURE_FLAG_ENV = "LORA_ENABLE_HYPO"
    run_mod = types.ModuleType(f"{package}.run")
    run_mod.handle_run = lambda config, ctx: {"dispatched": config, "train_type": ctx.model_train_type}
    monkeypatch.setitem(sys.modules, package, types.ModuleType(package))
    monkeypatch.setitem(sys.modules, f"{package}.manifest", manifest_mod)
    monkeypatch.setitem(sys.modules, f"{package}.run", run_mod)

    from mikazuki.engines.manifest import load_manifest
    from mikazuki.engines.registry import EnginePack

    real_packs = registry.discover_packs()
    hypo = EnginePack(manifest=load_manifest(manifest_mod), package=package)
    monkeypatch.setattr(registry, "discover_packs", lambda: {**real_packs, "hypo": hypo})

    result = dispatch_run("hypo-lora", {"foo": 1}, RunContext(timestamp="t", autosave_dir="/tmp", model_train_type="hypo-lora"))
    assert result == {"dispatched": {"foo": 1}, "train_type": "hypo-lora"}
    assert dispatch_run("no-such-type", {}, RunContext(timestamp="t", autosave_dir="/tmp")) is None


def test_dispatch_passes_variant_in_context(monkeypatch):
    """(engine, variant) contract: the registry variant reaches the handler."""
    import sys
    import types

    package = "mikazuki.engines.hypo2"
    manifest_mod = types.ModuleType(f"{package}.manifest")
    manifest_mod.ENGINE_ID = "hypo2"
    manifest_mod.KIND = KIND_PLUGIN
    manifest_mod.TRAIN_TYPES = {"hypo2-lora": "base-9b"}
    manifest_mod.UPSTREAM = {"repo": "example/hypo2", "commit": "abc123", "zip": None, "github": "https://github.com/example/hypo2.git", "gitee": None}
    manifest_mod.FEATURE_FLAG_ENV = "LORA_ENABLE_HYPO2"
    run_mod = types.ModuleType(f"{package}.run")
    run_mod.handle_run = lambda config, ctx: {"variant": ctx.variant}
    monkeypatch.setitem(sys.modules, package, types.ModuleType(package))
    monkeypatch.setitem(sys.modules, f"{package}.manifest", manifest_mod)
    monkeypatch.setitem(sys.modules, f"{package}.run", run_mod)

    from mikazuki.engines.manifest import load_manifest
    from mikazuki.engines.registry import EnginePack

    real_packs = registry.discover_packs()
    hypo = EnginePack(manifest=load_manifest(manifest_mod), package=package)
    monkeypatch.setattr(registry, "discover_packs", lambda: {**real_packs, "hypo2": hypo})

    result = dispatch_run("hypo2-lora", {}, RunContext(timestamp="t", autosave_dir="/tmp", model_train_type="hypo2-lora"))
    assert result == {"variant": "base-9b"}

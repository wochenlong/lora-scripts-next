"""Registry discovery: both migrated packs are found and train_types map."""

from mikazuki.engines import registry
from mikazuki.engines.manifest import KIND_PLUGIN


def test_discovers_migrated_packs():
    packs = registry.discover_packs()
    assert set(packs) == {"musubi", "anima-fast"}
    for pack in packs.values():
        assert pack.manifest.kind == KIND_PLUGIN
        assert pack.manifest.upstream["repo"]
        assert "github" in pack.manifest.upstream
        assert "gitee" in pack.manifest.upstream
        assert "zip" in pack.manifest.upstream


def test_train_type_mapping():
    mapping = registry.train_type_map()
    assert mapping["krea2-lora"] == ("musubi", "krea2")
    assert mapping["anima-lora-fast"] == ("anima-fast", "anima")


def test_resolve_train_type_roundtrip():
    pack, variant = registry.resolve_train_type("krea2-lora")
    assert pack.engine_id == "musubi"
    assert variant == "krea2"
    assert registry.resolve_train_type("no-such-type") is None


def test_pack_modules_importable():
    pack = registry.get_pack("musubi")
    adapter = pack.import_module("adapter")
    assert adapter is not None

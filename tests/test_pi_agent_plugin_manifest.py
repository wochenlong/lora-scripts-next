import json
from pathlib import Path

from mikazuki.plugin_marketplace.models import PluginManifest


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugin-packages" / "next-trainer-pi-agent"

EXPECTED_BRIDGE_METHODS = {
    "session.list",
    "session.create",
    "session.rename",
    "session.delete",
    "session.getState",
    "session.getHistory",
    "session.getThinking",
    "session.prompt",
    "session.cancel",
    "session.compact",
    "session.setModel",
    "session.setThinkingLevel",
    "session.recallQueue",
    "session.subscribe",
    "provider.list",
    "provider.status",
    "provider.saveKey",
    "provider.removeKey",
    "provider.test",
    "resource.pick",
    "resource.getSummary",
    "artifact.open",
    "artifact.download",
    "confirmation.request",
    "confirmation.getResult",
    "navigation.openExternal",
    "navigation.openPluginRoute",
    "theme.get",
    "locale.get",
    "context.get",
}


def load_manifest() -> PluginManifest:
    value = json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"))
    return PluginManifest.model_validate(value)


def test_real_agent_manifest_covers_the_complete_bridge_contract():
    manifest = load_manifest()
    requests = {item.method for item in manifest.bridge.requests}
    streams = {item.method for item in manifest.bridge.streams}

    assert requests | streams == EXPECTED_BRIDGE_METHODS
    assert streams == {"session.subscribe"}
    assert len(requests) + len(streams) == len(EXPECTED_BRIDGE_METHODS)
    assert all(item.permission in manifest.permissions for item in manifest.bridge.requests)
    assert all(item.permission in manifest.permissions for item in manifest.bridge.streams)


def test_real_agent_manifest_keeps_runtime_and_ui_in_the_plugin_package():
    manifest = load_manifest()

    assert manifest.id == "next-trainer-pi-agent"
    assert manifest.protocol_version == "1"
    assert manifest.runtime.build_node == "22.19.0"
    assert manifest.runtime.embedded_runtime == "bun-1.4.0"
    assert manifest.runtime.entrypoint == "bin/next-trainer-pi-agent.exe"
    assert manifest.ui.entrypoint == "ui/index.html"
    assert manifest.ui.settings_entrypoint == "ui/settings.html"
    assert manifest.install_hooks == []
    assert (PLUGIN_ROOT / manifest.ui.entrypoint).is_file()
    assert (PLUGIN_ROOT / manifest.ui.settings_entrypoint).is_file()
    assert (PLUGIN_ROOT / manifest.package.sbom).is_file()


def test_plugin_html_entries_have_no_inline_script_authority():
    for name in ("index.html", "settings.html"):
        html = (PLUGIN_ROOT / "ui" / name).read_text(encoding="utf-8")
        assert '<script type="module" src="./index.js"></script>' in html
        assert html.count("<script") == 1
        assert "http://" not in html
        assert "https://" not in html

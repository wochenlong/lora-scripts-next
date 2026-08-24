import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "katex/dist/katex.min.css";

import { BridgeAgentTransport, BridgeHostCapabilities } from "./bridge/bridge-transport.ts";
import { PluginBridgeClient, type BridgeWelcome } from "./bridge/plugin-bridge-client.ts";
import { AgentChatPanel } from "./components/AgentChatPanel.tsx";
import { ProviderSettingsPanel } from "./components/ProviderSettingsPanel.tsx";
import type { ThemeTokens } from "./contracts/host-capabilities.ts";
import { I18nProvider, type UiLocale } from "./i18n/I18nProvider.tsx";
import { ThemeProvider } from "./theme/ThemeProvider.tsx";
import { mapHostTheme } from "./theme/host-theme.ts";
import "./app.css";

const PLUGIN_ID = "next-trainer-pi-agent";

interface RuntimeState {
  welcome: BridgeWelcome;
  bridge: PluginBridgeClient;
  transport: BridgeAgentTransport;
  host: BridgeHostCapabilities;
  scheme: "light" | "dark";
  theme: ThemeTokens;
  locale: UiLocale;
}

function PluginApplication() {
  const [runtime, setRuntime] = useState<RuntimeState | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const bridge = new PluginBridgeClient({ pluginId: PLUGIN_ID });
    let transport: BridgeAgentTransport | null = null;
    let unsubscribeHostState = () => {};
    void bridge.start().then(async (welcome) => {
      if (!active) return;
      transport = new BridgeAgentTransport(bridge);
      const fallbackTheme = mapHostTheme(welcome.themeTokens, "light");
      const host = new BridgeHostCapabilities(bridge, welcome.locale, fallbackTheme);
      const context = await host.environment.getContext().catch(() => null);
      const scheme = context?.colorScheme === "dark" ? "dark" : "light";
      const rawTheme = await host.environment.getTheme().catch(() => welcome.themeTokens as unknown as ThemeTokens);
      const theme = mapHostTheme(rawTheme as unknown as Record<string, string>, scheme);
      if (!active) return;
      const locale: UiLocale = welcome.locale === "zh-CN" ? "zh-CN" : "en";
      setRuntime({ welcome, bridge, transport, host, scheme, theme, locale });
      unsubscribeHostState = bridge.onHostState((state) => {
        if (!active) return;
        setRuntime((current) => current ? {
          ...current,
          scheme: state.colorScheme,
          theme: mapHostTheme(state.themeTokens, state.colorScheme),
          locale: state.locale === "zh-CN" ? "zh-CN" : "en",
        } : current);
      });
    }).catch(() => {
      if (active) setError("Unable to connect to the Next Trainer plugin host.");
    });
    return () => {
      active = false;
      unsubscribeHostState();
      transport?.dispose();
      bridge.close();
    };
  }, []);

  if (error) return <main className="nta-bootstrap-state" role="alert">{error}</main>;
  if (!runtime) return <main className="nta-bootstrap-state" aria-busy="true">Connecting…</main>;

  const view = window.location.pathname.endsWith("/settings.html")
    ? "settings"
    : new URLSearchParams(window.location.search).get("view");
  return (
    <I18nProvider locale={runtime.locale}>
      <ThemeProvider tokens={runtime.theme} scheme={runtime.scheme}>
        {view === "settings"
          ? <ProviderSettingsPanel transport={runtime.transport} />
          : (
            <AgentChatPanel
              transport={runtime.transport}
              host={runtime.host}
              initialSessionId={runtime.welcome.activeSession}
            />
          )}
      </ThemeProvider>
    </I18nProvider>
  );
}

const root = document.getElementById("root");
if (!root) throw new Error("Plugin UI root element is missing.");
createRoot(root).render(<StrictMode><PluginApplication /></StrictMode>);

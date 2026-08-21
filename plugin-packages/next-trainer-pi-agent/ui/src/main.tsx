import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "katex/dist/katex.min.css";

import { BridgeAgentTransport, BridgeHostCapabilities } from "./bridge/bridge-transport.ts";
import { PluginBridgeClient, type BridgeWelcome } from "./bridge/plugin-bridge-client.ts";
import { AgentChatPanel } from "./components/AgentChatPanel.tsx";
import { ProviderSettingsPanel } from "./components/ProviderSettingsPanel.tsx";
import type { ThemeTokens } from "./contracts/host-capabilities.ts";
import { I18nProvider, type UiLocale } from "./i18n/I18nProvider.tsx";
import { DEFAULT_DARK_THEME, DEFAULT_LIGHT_THEME, ThemeProvider } from "./theme/ThemeProvider.tsx";
import "./app.css";

const PLUGIN_ID = "next-trainer-pi-agent";

function tokenValue(tokens: Record<string, string>, names: string[], fallback: string): string {
  for (const name of names) {
    const value = tokens[name]?.trim();
    if (value) return value;
  }
  return fallback;
}

export function mapHostTheme(tokens: Record<string, string>, scheme: "light" | "dark"): ThemeTokens {
  const fallback = scheme === "dark" ? DEFAULT_DARK_THEME : DEFAULT_LIGHT_THEME;
  return {
    background: tokenValue(tokens, ["background", "--bg"], fallback.background),
    panel: tokenValue(tokens, ["panel", "--surface"], fallback.panel),
    text: tokenValue(tokens, ["text", "--text"], fallback.text),
    mutedText: tokenValue(tokens, ["mutedText", "--text-soft"], fallback.mutedText),
    border: tokenValue(tokens, ["border", "--border"], fallback.border),
    accent: tokenValue(tokens, ["accent", "--accent"], fallback.accent),
    accentText: tokenValue(tokens, ["accentText", "--accent-text"], fallback.accentText),
    danger: tokenValue(tokens, ["danger", "--danger"], fallback.danger),
    radius: tokenValue(tokens, ["radius", "--radius"], fallback.radius),
    fontFamily: tokenValue(tokens, ["fontFamily", "--font-family"], fallback.fontFamily),
    monoFontFamily: tokenValue(tokens, ["monoFontFamily", "--mono-font-family"], fallback.monoFontFamily),
  };
}

interface RuntimeState {
  welcome: BridgeWelcome;
  bridge: PluginBridgeClient;
  transport: BridgeAgentTransport;
  host: BridgeHostCapabilities;
  scheme: "light" | "dark";
  theme: ThemeTokens;
}

function PluginApplication() {
  const [runtime, setRuntime] = useState<RuntimeState | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const bridge = new PluginBridgeClient({ pluginId: PLUGIN_ID });
    let transport: BridgeAgentTransport | null = null;
    void bridge.start().then(async (welcome) => {
      if (!active) return;
      transport = new BridgeAgentTransport(bridge);
      const fallbackTheme = mapHostTheme(welcome.themeTokens, "light");
      const host = new BridgeHostCapabilities(bridge, welcome.locale, fallbackTheme);
      const context = await host.environment.getContext().catch(() => null);
      const scheme = context?.colorScheme === "dark" ? "dark" : "light";
      const theme = await host.environment.getTheme().catch(() => mapHostTheme(welcome.themeTokens, scheme));
      if (!active) return;
      setRuntime({ welcome, bridge, transport, host, scheme, theme });
    }).catch(() => {
      if (active) setError("Unable to connect to the Next Trainer plugin host.");
    });
    return () => {
      active = false;
      transport?.dispose();
      bridge.close();
    };
  }, []);

  if (error) return <main className="nta-bootstrap-state" role="alert">{error}</main>;
  if (!runtime) return <main className="nta-bootstrap-state" aria-busy="true">Connecting…</main>;

  const locale: UiLocale = runtime.welcome.locale === "zh-CN" ? "zh-CN" : "en";
  const view = window.location.pathname.endsWith("/settings.html")
    ? "settings"
    : new URLSearchParams(window.location.search).get("view");
  return (
    <I18nProvider locale={locale}>
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

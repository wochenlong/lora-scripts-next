import { createContext, useContext, useMemo, type CSSProperties, type ReactNode } from "react";

import type { ThemeTokens } from "../contracts/host-capabilities.ts";

export const DEFAULT_LIGHT_THEME: ThemeTokens = {
  background: "#f6f7f9",
  panel: "#ffffff",
  text: "#1c2430",
  mutedText: "#667085",
  border: "#d8dee8",
  accent: "#2f80ed",
  accentText: "#ffffff",
  danger: "#c62828",
  radius: "12px",
  fontFamily: "Inter, system-ui, sans-serif",
  monoFontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace",
};

export const DEFAULT_DARK_THEME: ThemeTokens = {
  background: "#11161d",
  panel: "#1a212b",
  text: "#ecf1f7",
  mutedText: "#9aa6b5",
  border: "#303a48",
  accent: "#4f9cf9",
  accentText: "#08111d",
  danger: "#ff6b6b",
  radius: "12px",
  fontFamily: "Inter, system-ui, sans-serif",
  monoFontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace",
};

interface ThemeContextValue {
  tokens: ThemeTokens;
  scheme: "light" | "dark";
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function toStyle(tokens: ThemeTokens): CSSProperties {
  return {
    "--nta-bg": tokens.background,
    "--nta-panel": tokens.panel,
    "--nta-text": tokens.text,
    "--nta-muted": tokens.mutedText,
    "--nta-border": tokens.border,
    "--nta-accent": tokens.accent,
    "--nta-accent-text": tokens.accentText,
    "--nta-danger": tokens.danger,
    "--nta-radius": tokens.radius,
    "--nta-font": tokens.fontFamily,
    "--nta-mono": tokens.monoFontFamily,
  } as CSSProperties;
}

export function ThemeProvider({
  tokens,
  scheme,
  children,
}: {
  tokens: ThemeTokens;
  scheme: "light" | "dark";
  children: ReactNode;
}) {
  const value = useMemo(() => ({ tokens, scheme }), [tokens, scheme]);
  return (
    <ThemeContext.Provider value={value}>
      <div className="nta-theme-root" data-color-scheme={scheme} style={toStyle(tokens)}>
        {children}
      </div>
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used inside ThemeProvider");
  return context;
}

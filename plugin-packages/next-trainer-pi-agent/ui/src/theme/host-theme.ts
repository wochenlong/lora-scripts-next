import type { ThemeTokens } from "../contracts/host-capabilities.ts";
import { DEFAULT_DARK_THEME, DEFAULT_LIGHT_THEME } from "./ThemeProvider.tsx";

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
    accentText: tokenValue(tokens, ["accentText", "--accent-contrast", "--accent-text"], fallback.accentText),
    danger: tokenValue(tokens, ["danger", "--danger"], fallback.danger),
    radius: tokenValue(tokens, ["radius", "--radius"], fallback.radius),
    fontFamily: tokenValue(tokens, ["fontFamily", "--font-family"], fallback.fontFamily),
    monoFontFamily: tokenValue(tokens, ["monoFontFamily", "--mono-font-family"], fallback.monoFontFamily),
  };
}

import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { mapHostTheme } from "../src/theme/host-theme.ts";
import { ThemeProvider } from "../src/theme/ThemeProvider.tsx";

describe("host theme adaptation", () => {
  test("maps the host CSS token vocabulary instead of passing it through as a ThemeTokens object", () => {
    const theme = mapHostTheme({
      "--bg": "#0d1117",
      "--surface": "#161b22",
      "--text": "#e6edf3",
      "--text-soft": "#b1bac4",
      "--border": "#30363d",
      "--accent": "#4493f8",
      "--accent-contrast": "#ffffff",
      "--danger": "#f85149",
      "--radius": "8px",
    }, "dark");
    render(<ThemeProvider tokens={theme} scheme="dark"><span>content</span></ThemeProvider>);
    const root = screen.getByText("content").parentElement as HTMLElement;
    expect(root.dataset.colorScheme).toBe("dark");
    expect(root.style.getPropertyValue("--nta-bg")).toBe("#0d1117");
    expect(root.style.getPropertyValue("--nta-panel")).toBe("#161b22");
    expect(root.style.getPropertyValue("--nta-accent-text")).toBe("#ffffff");
    expect(root.style.getPropertyValue("--nta-radius")).toBe("8px");
  });

  test("uses complete light defaults when the host omits optional tokens", () => {
    const theme = mapHostTheme({}, "light");
    expect(theme.background).toBe("#f6f7f9");
    expect(theme.text).toBe("#1c2430");
    expect(theme.fontFamily).toContain("Inter");
  });
});

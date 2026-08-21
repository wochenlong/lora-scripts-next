import type { ReactNode } from "react";

import { I18nProvider, type UiLocale } from "../i18n/I18nProvider.tsx";
import {
  DEFAULT_DARK_THEME,
  DEFAULT_LIGHT_THEME,
  ThemeProvider,
} from "../theme/ThemeProvider.tsx";

export function SlimUiTestWrapper({
  children,
  locale = "zh-CN",
  scheme = "light",
}: {
  children: ReactNode;
  locale?: UiLocale;
  scheme?: "light" | "dark";
}) {
  return (
    <I18nProvider locale={locale}>
      <ThemeProvider tokens={scheme === "dark" ? DEFAULT_DARK_THEME : DEFAULT_LIGHT_THEME} scheme={scheme}>
        {children}
      </ThemeProvider>
    </I18nProvider>
  );
}

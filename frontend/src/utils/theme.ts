export const THEME_KEY = "vuepress-color-scheme"
export type ThemeName = "light" | "dark"

export function getTheme(): ThemeName {
  if (typeof document !== "undefined" && document.documentElement.classList.contains("dark")) return "dark"
  try {
    return localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light"
  } catch {
    return "light"
  }
}

export function setTheme(theme: ThemeName) {
  document.documentElement.classList.toggle("dark", theme === "dark")
  try {
    localStorage.setItem(THEME_KEY, theme)
  } catch { /* storage unavailable */ }
}

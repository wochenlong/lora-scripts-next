import { ref } from 'vue'
import { appTranslations } from './app-translations'
import { panelTranslations } from './panels-translations'

export type LauncherLocale = 'zh-CN' | 'en-US'
export const locale = ref<LauncherLocale>('zh-CN')
const english: Record<string, string> = { ...appTranslations, ...panelTranslations }

/** Product labels only. Backend diagnostics, paths and original log records stay intact. */
export function t(source: string, params: Record<string, string | number> = {}): string {
  const text = locale.value === 'en-US' ? english[source] ?? source : source
  return text.replace(/\{(\w+)\}/g, (placeholder, key: string) =>
    Object.prototype.hasOwnProperty.call(params, key) ? String(params[key]) : placeholder)
}

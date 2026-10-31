import { formatBytes as formatRawBytes } from './bytes'
import { t } from './i18n'

/** Translate missing or invalid sizes while preserving numeric units and the pure formatter. */
export function formatBytes(bytes: number | null): string {
  return t(formatRawBytes(bytes))
}

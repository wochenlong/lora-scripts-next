export function formatBytes(bytes: number | null): string {
  if (bytes === null) return '未提供'
  if (!Number.isFinite(bytes) || bytes < 0) return '无法读取'
  if (!Number.isSafeInteger(bytes)) return '超出界面精确显示范围'
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB']
  let value = bytes
  let index = 0
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1 }
  return `${value.toFixed(index ? 2 : 0)} ${units[index]}`
}

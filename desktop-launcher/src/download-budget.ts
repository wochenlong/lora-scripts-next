export type BudgetUnit = 'B' | 'MiB' | 'GiB'
export interface BudgetDraft { value: string; unit: BudgetUnit; expectedRevision: number | null }

const factors: Record<BudgetUnit, bigint> = { B: 1n, MiB: 1024n ** 2n, GiB: 1024n ** 3n }

// 整数字符串与BigInt避免浮点换算悄悄四舍五入用户设置的硬上限。
export function parseBudgetCap(value: string, unit: BudgetUnit): number {
  const text = value.trim()
  if (text.length > 32 || !/^\d+$/.test(text)) throw new Error('请填写大于零的整数额度，并选择单位。')
  const bytes = BigInt(text) * factors[unit]
  if (bytes <= 0n || bytes > BigInt(Number.MAX_SAFE_INTEGER)) throw new Error('额度必须大于零，且不超过 9,007,199,254,740,991 字节。')
  return Number(bytes)
}

export function budgetDraft(cap: number | null, expectedRevision: number | null): BudgetDraft {
  if (cap === null) return { value: '', unit: 'GiB', expectedRevision }
  if (!Number.isSafeInteger(cap) || cap <= 0) return { value: '', unit: 'B', expectedRevision }
  for (const unit of ['GiB', 'MiB'] as const) {
    const factor = Number(factors[unit])
    if (cap % factor === 0) return { value: String(cap / factor), unit, expectedRevision }
  }
  return { value: String(cap), unit: 'B', expectedRevision }
}

export function formatBudgetBytes(bytes: number | null): string {
  if (bytes === null) return '未设置'
  if (!Number.isFinite(bytes) || bytes < 0) return '无法读取'
  if (!Number.isSafeInteger(bytes)) return '超出界面精确显示范围'
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB']
  let value = bytes
  let index = 0
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1 }
  return `${value.toFixed(index ? 2 : 0)} ${units[index]}`
}

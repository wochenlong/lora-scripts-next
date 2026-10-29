import assert from 'node:assert/strict'
import test from 'node:test'
import { budgetDraft, formatBudgetBytes, parseBudgetCap } from '../src/download-budget.ts'

test('an unset policy produces an empty draft; zero never means unlimited', () => {
  assert.deepEqual(budgetDraft(null, null), { value: '', unit: 'GiB', expectedRevision: null })
  for (const value of ['', '0', '-1', 'NaN', 'Infinity', '1e3', '1.5', '0x10']) {
    assert.throws(() => parseBudgetCap(value, 'GiB'))
  }
})

test('cap conversion is exact and rejects numbers outside IPC safe integer range', () => {
  assert.equal(parseBudgetCap('3', 'GiB'), 3 * 1024 ** 3)
  assert.equal(parseBudgetCap(' 17 ', 'MiB'), 17 * 1024 ** 2)
  assert.equal(parseBudgetCap('9007199254740991', 'B'), Number.MAX_SAFE_INTEGER)
  assert.throws(() => parseBudgetCap('9007199254740992', 'B'))
  assert.throws(() => parseBudgetCap('8388608', 'GiB'))
})

test('existing caps round trip exactly and retain the revision for CAS', () => {
  for (const cap of [1, 1_000_000_001, 17 * 1024 ** 2, 3 * 1024 ** 3, Number.MAX_SAFE_INTEGER]) {
    const draft = budgetDraft(cap, 42)
    assert.equal(draft.expectedRevision, 42)
    assert.equal(parseBudgetCap(draft.value, draft.unit), cap)
  }
  assert.equal(budgetDraft(Number.MAX_SAFE_INTEGER + 1, 43).value, '')
})

test('zero usage is displayed as zero and unavailable cap is distinct', () => {
  assert.equal(formatBudgetBytes(0), '0 B')
  assert.equal(formatBudgetBytes(null), '未设置')
  assert.equal(formatBudgetBytes(Number.MAX_SAFE_INTEGER + 1), '超出界面精确显示范围')
})

import assert from 'node:assert/strict'
import test from 'node:test'
import { formatBytes } from '../src/bytes.ts'

test('file size formatting distinguishes zero, absent values and unsafe integers', () => {
  assert.equal(formatBytes(0), '0 B')
  assert.equal(formatBytes(null), '未提供')
  assert.equal(formatBytes(1024), '1.00 KiB')
  assert.equal(formatBytes(Number.MAX_SAFE_INTEGER + 1), '超出界面精确显示范围')
})

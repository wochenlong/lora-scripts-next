import assert from 'node:assert/strict'
import test from 'node:test'
import { settingsForSave } from '../src/network-settings.ts'

const draft = (mode = 'auto') => ({ mode, http_proxy: '', https_proxy: '', no_proxy: '' })

test('saving an unrelated mode edit preserves absent, null and explicit disabled fields', () => {
  for (const saved of [
    { mode: 'auto' },
    { mode: 'auto', http_proxy: null, no_proxy: null },
    { mode: 'auto', http_proxy: '', https_proxy: '' },
  ]) {
    assert.deepEqual(settingsForSave(saved, draft('system'), []), { ...saved, mode: 'system' })
  }
})

test('clearing a configured proxy explicitly disables it; inheritance removes the override', () => {
  const saved = { mode: 'auto', http_proxy: 'http://localhost:11809' }
  assert.deepEqual(settingsForSave(saved, draft(), []), { mode: 'auto', http_proxy: '' })
  assert.deepEqual(settingsForSave(saved, draft(), ['http_proxy']), { mode: 'auto' })
  assert.deepEqual(settingsForSave({ mode: 'auto', http_proxy: '' }, draft(), ['http_proxy']), { mode: 'auto' })
})

test('editing one protocol preserves the other overrides exactly', () => {
  const saved = { mode: 'manual', http_proxy: null, https_proxy: '', no_proxy: '.local' }
  const edited = { ...draft('manual'), http_proxy: ' localhost:11809 ', no_proxy: '.local' }
  assert.deepEqual(settingsForSave(saved, edited, []), { ...saved, http_proxy: 'localhost:11809' })
})

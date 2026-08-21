import assert from "node:assert/strict"
import test from "node:test"
import { startParentMonitor } from "../../src/parent-monitor.ts"

test("parent monitor invokes shutdown once when the Host process disappears", async () => {
  let alive = true
  let shutdowns = 0
  const monitor = startParentMonitor(() => alive, () => { shutdowns += 1 }, 5)
  await new Promise((resolve) => setTimeout(resolve, 15))
  assert.equal(shutdowns, 0)
  alive = false
  await new Promise((resolve) => setTimeout(resolve, 20))
  assert.equal(shutdowns, 1)
  monitor.stop()
})

test("stopping parent monitor prevents later shutdown", async () => {
  let shutdowns = 0
  const monitor = startParentMonitor(() => false, () => { shutdowns += 1 }, 20)
  monitor.stop()
  await new Promise((resolve) => setTimeout(resolve, 30))
  assert.equal(shutdowns, 0)
})

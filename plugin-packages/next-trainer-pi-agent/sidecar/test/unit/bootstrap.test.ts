import assert from "node:assert/strict"
import test from "node:test"
import path from "node:path"
import { parseBootstrap } from "../../src/bootstrap.ts"
import { SidecarError } from "../../src/errors.ts"

const baseEnv: NodeJS.ProcessEnv = {
  NEXT_TRAINER_SIDECAR_TOKEN: "a".repeat(32),
  NEXT_TRAINER_HOST_TOOL_TOKEN: "b".repeat(32),
  NEXT_TRAINER_PLUGIN_DATA_ROOT: path.resolve(".runtime", "test"),
  NEXT_TRAINER_PARENT_PID: "123",
  NEXT_TRAINER_SIDECAR_PORT: "0",
  NEXT_TRAINER_HOST_TOOL_BASE_URL: "http://127.0.0.1:28000",
}

test("bootstrap accepts only controlled loopback inputs", () => {
  const config = parseBootstrap(baseEnv)
  assert.equal(config.port, 0)
  assert.equal(config.parentPid, 123)
  assert.equal(config.hostToolBaseUrl, "http://127.0.0.1:28000")
})

test("bootstrap rejects a non-loopback Host Tool gateway", () => {
  assert.throws(
    () => parseBootstrap({ ...baseEnv, NEXT_TRAINER_HOST_TOOL_BASE_URL: "https://example.com" }),
    (error: unknown) => error instanceof SidecarError && error.code === "BOOTSTRAP_INVALID",
  )
})

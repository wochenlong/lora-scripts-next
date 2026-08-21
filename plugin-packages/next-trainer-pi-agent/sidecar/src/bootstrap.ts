import path from "node:path"
import { SidecarError } from "./errors.ts"

export interface BootstrapConfig {
  port: number
  token: string
  hostToolToken: string
  pluginDataRoot: string
  parentPid: number
  hostToolBaseUrl: string | null
}

function requiredSecret(env: NodeJS.ProcessEnv, name: string): string {
  const value = env[name]
  if (!value || value.length < 32) {
    throw new SidecarError(500, "BOOTSTRAP_INVALID", `${name} must contain at least 32 characters.`)
  }
  return value
}

function parsePort(value: string | undefined): number {
  const port = Number(value ?? "0")
  if (!Number.isInteger(port) || port < 0 || port > 65535) {
    throw new SidecarError(500, "BOOTSTRAP_INVALID", "NEXT_TRAINER_SIDECAR_PORT must be an integer from 0 to 65535.")
  }
  return port
}

function parseParentPid(value: string | undefined): number {
  const parentPid = Number(value)
  if (!Number.isInteger(parentPid) || parentPid <= 0) {
    throw new SidecarError(500, "BOOTSTRAP_INVALID", "NEXT_TRAINER_PARENT_PID must be a positive integer.")
  }
  return parentPid
}

function parseLoopbackBaseUrl(value: string | undefined): string | null {
  if (!value) return null
  const url = new URL(value)
  if (url.protocol !== "http:" || url.hostname !== "127.0.0.1" || url.username || url.password) {
    throw new SidecarError(500, "BOOTSTRAP_INVALID", "Host Tool base URL must use http://127.0.0.1.")
  }
  url.hash = ""
  url.search = ""
  return url.toString().replace(/\/$/, "")
}

export function parseBootstrap(env: NodeJS.ProcessEnv = process.env): BootstrapConfig {
  const dataRoot = env.NEXT_TRAINER_PLUGIN_DATA_ROOT
  if (!dataRoot || !path.isAbsolute(dataRoot)) {
    throw new SidecarError(500, "BOOTSTRAP_INVALID", "NEXT_TRAINER_PLUGIN_DATA_ROOT must be an absolute path.")
  }

  return {
    port: parsePort(env.NEXT_TRAINER_SIDECAR_PORT),
    token: requiredSecret(env, "NEXT_TRAINER_SIDECAR_TOKEN"),
    hostToolToken: requiredSecret(env, "NEXT_TRAINER_HOST_TOOL_TOKEN"),
    pluginDataRoot: path.resolve(dataRoot),
    parentPid: parseParentPid(env.NEXT_TRAINER_PARENT_PID),
    hostToolBaseUrl: parseLoopbackBaseUrl(env.NEXT_TRAINER_HOST_TOOL_BASE_URL),
  }
}

import { defineTool, type ToolDefinition } from "@earendil-works/pi-coding-agent"
import { Type } from "typebox"
import { SidecarError } from "./errors.ts"

interface HostToolDefinition {
  name: string
  label: string
  description: string
  parameters: Record<string, unknown>
}

interface HostToolDefinitionResponse {
  ok: boolean
  data?: { tools?: HostToolDefinition[] }
}

interface HostToolExecutionResponse {
  ok: boolean
  data?: unknown
  error?: { code?: string; message?: string }
  details?: unknown
  audit_id?: string
}

export interface HostToolFactoryOptions {
  baseUrl: string
  token: string
  fetchImpl?: typeof fetch
}

const TOOL_NAME = /^[a-z][a-z0-9_]{0,63}$/
const RESERVED_TOOLS = new Set(["read", "bash", "edit", "write", "grep", "find", "ls"])

async function fetchJson<T>(
  fetchImpl: typeof fetch,
  url: string,
  init: RequestInit,
  failureCode: string,
): Promise<T> {
  const response = await fetchImpl(url, { ...init, redirect: "manual" })
  if (response.status >= 300 && response.status < 400) {
    await response.body?.cancel().catch(() => undefined)
    throw new SidecarError(502, "HOST_TOOL_REDIRECT_BLOCKED", "Host Tool gateway redirects are not allowed.")
  }
  if (!response.ok) {
    await response.body?.cancel().catch(() => undefined)
    throw new SidecarError(502, failureCode, "The Host Tool gateway request failed.", true)
  }
  try {
    return await response.json() as T
  } catch {
    throw new SidecarError(502, failureCode, "The Host Tool gateway returned invalid JSON.")
  }
}

export function createHostToolFactory(options: HostToolFactoryOptions): (sessionId: string) => Promise<ToolDefinition[]> {
  const baseUrl = options.baseUrl.replace(/\/$/, "")
  const fetchImpl = options.fetchImpl ?? fetch
  return async (sessionId: string): Promise<ToolDefinition[]> => {
    const catalog = await fetchJson<HostToolDefinitionResponse>(
      fetchImpl,
      `${baseUrl}/internal/agent-tools/definitions`,
      { headers: { authorization: `Bearer ${options.token}`, "x-next-trainer-session-id": sessionId } },
      "HOST_TOOL_CATALOG_UNAVAILABLE",
    )
    if (!catalog.ok || !Array.isArray(catalog.data?.tools)) {
      throw new SidecarError(502, "HOST_TOOL_CATALOG_INVALID", "The Host Tool catalog is invalid.")
    }

    return catalog.data.tools.map((definition) => {
      if (!TOOL_NAME.test(definition.name) || RESERVED_TOOLS.has(definition.name)) {
        throw new SidecarError(502, "HOST_TOOL_CATALOG_INVALID", "The Host Tool catalog contains an invalid Tool name.")
      }
      if (!definition.label || !definition.description || definition.parameters?.type !== "object") {
        throw new SidecarError(502, "HOST_TOOL_CATALOG_INVALID", "The Host Tool catalog contains an invalid Tool definition.")
      }
      return defineTool({
        name: definition.name,
        label: definition.label,
        description: definition.description,
        parameters: Type.Unsafe(definition.parameters),
        execute: async (toolCallId, params, signal) => {
          const result = await fetchJson<HostToolExecutionResponse>(
            fetchImpl,
            `${baseUrl}/internal/agent-tools/${encodeURIComponent(definition.name)}`,
            {
              method: "POST",
              headers: {
                authorization: `Bearer ${options.token}`,
                "content-type": "application/json",
                "x-next-trainer-session-id": sessionId,
                "x-next-trainer-tool-call-id": toolCallId,
              },
              body: JSON.stringify({ arguments: params }),
              ...(signal ? { signal } : {}),
            },
            "HOST_TOOL_EXECUTION_FAILED",
          )
          if (!result.ok) {
            throw new SidecarError(502, "HOST_TOOL_EXECUTION_FAILED", "The Host Tool reported a failure.")
          }
          const text = typeof result.data === "string" ? result.data : JSON.stringify(result.data ?? null)
          return {
            content: [{ type: "text", text }],
            details: { auditId: result.audit_id ?? null, hostDetails: result.details ?? null },
          }
        },
      })
    })
  }
}

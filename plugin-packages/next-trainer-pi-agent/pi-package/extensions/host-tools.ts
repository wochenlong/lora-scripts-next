/**
 * Next Trainer host-Tool bridge (pi extension).
 *
 * Registers the host's agent-tools catalog (training-config, dataset, metrics,
 * artifacts, knowledge, Civitai, tagger) as pi-native tools. Each registered
 * tool is a thin loopback HTTP call to the host gateway
 * (``<NEXT_TRAINER_HOST_TOOL_BASE_URL>/internal/agent-tools/...``) using the
 * per-launch Bearer token the host injects into the plugin environment.
 *
 * Fail-closed: if the gateway credentials are absent, the catalog is
 * unreachable, or an entry is invalid/reserved, the tool is simply not
 * registered — the session never sees a broken or unauthorized tool. The host
 * remains authoritative for validation, least privilege, confirmation tickets
 * and audit; this module only translates the Tool boundary.
 *
 * The session id sent with every execution is the live pi session id
 * (``ctx.sessionManager.getSessionId()``), so host-side session-scoped state
 * (caption overlays, change sets, scoped workspaces) and audit lines up with
 * the pi session the user is actually talking to.
 */
import { Type } from "typebox";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

interface HostToolDefinition {
  name: string;
  label: string;
  description: string;
  parameters: Record<string, unknown>;
}

interface HostToolDefinitionResponse {
  ok: boolean;
  data?: { tools?: HostToolDefinition[] };
}

interface HostToolExecutionResponse {
  ok: boolean;
  data?: unknown;
  audit_id?: string;
  details?: unknown;
}

const TOOL_NAME = /^[a-z][a-z0-9_]{0,63}$/;
const RESERVED_TOOLS = new Set(["read", "bash", "edit", "write", "grep", "find", "ls"]);

function warn(message: string, ...rest: unknown[]): void {
  try {
    console.warn("[next-trainer:host-tools]", message, ...rest);
  } catch {
    /* diagnostics must never break extension loading */
  }
}

async function fetchJson<T>(url: string, init: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, redirect: "manual" });
  if (response.status >= 300 && response.status < 400) {
    await response.body?.cancel().catch(() => undefined);
    throw new Error("Host Tool gateway redirects are not allowed.");
  }
  if (!response.ok) {
    // Surface the host's error detail (code + message) so the agent can see
    // WHY the call failed instead of blindly retrying.
    let detail = "";
    try {
      const raw = (await response.text()).slice(0, 4000);
      try {
        const parsed: unknown = JSON.parse(raw);
        const hostDetail = (parsed as { detail?: unknown } | null)?.detail;
        if (typeof hostDetail === "string") {
          detail = hostDetail;
        } else if (hostDetail && typeof hostDetail === "object") {
          const obj = hostDetail as { code?: unknown; message?: unknown };
          detail = [typeof obj.code === "string" ? obj.code : "", typeof obj.message === "string" ? obj.message : ""]
            .filter(Boolean)
            .join(": ");
        } else if (parsed && typeof parsed === "object") {
          const message = (parsed as { message?: unknown }).message;
          if (typeof message === "string") detail = message;
        }
        if (!detail) detail = raw;
      } catch {
        detail = raw;
      }
    } catch {
      detail = "";
    }
    throw new Error(`Host Tool gateway request failed (HTTP ${response.status})${detail ? `: ${detail}` : ""}.`);
  }
  try {
    return (await response.json()) as T;
  } catch {
    throw new Error("Host Tool gateway returned invalid JSON.");
  }
}

async function fetchCatalog(baseUrl: string, token: string): Promise<HostToolDefinition[]> {
  const catalog = await fetchJson<HostToolDefinitionResponse>(`${baseUrl}/internal/agent-tools/definitions`, {
    headers: { authorization: `Bearer ${token}` },
  });
  if (!catalog.ok || !Array.isArray(catalog.data?.tools)) {
    throw new Error("Host Tool catalog is invalid.");
  }
  return catalog.data.tools;
}

export default async function nextTrainerHostTools(pi: ExtensionAPI): Promise<void> {
  const baseUrl = (process.env.NEXT_TRAINER_HOST_TOOL_BASE_URL ?? "").replace(/\/+$/, "");
  const token = process.env.NEXT_TRAINER_HOST_TOOL_TOKEN ?? "";
  if (!baseUrl || token.length < 32) {
    return; // no gateway credentials (e.g. plain pi-web dev) -> no host tools
  }

  let catalog: HostToolDefinition[];
  try {
    catalog = await fetchCatalog(baseUrl, token);
  } catch (error) {
    warn("catalog unavailable; no host tools registered.", error instanceof Error ? error.message : String(error));
    return; // fail closed
  }

  let registered = 0;
  for (const definition of catalog) {
    if (!TOOL_NAME.test(definition.name) || RESERVED_TOOLS.has(definition.name)) {
      warn("skipping tool with invalid or reserved name:", definition.name);
      continue;
    }
    if (!definition.label || !definition.description || definition.parameters?.type !== "object") {
      warn("skipping tool with invalid definition:", definition.name);
      continue;
    }
    pi.registerTool({
      name: definition.name,
      label: definition.label,
      description: definition.description,
      promptSnippet: definition.label,
      parameters: Type.Unsafe(definition.parameters),
      execute: async (toolCallId, params, signal, _onUpdate, ctx) => {
        const sessionId = ctx.sessionManager.getSessionId();
        const result = await fetchJson<HostToolExecutionResponse>(
          `${baseUrl}/internal/agent-tools/${encodeURIComponent(definition.name)}`,
          {
            method: "POST",
            headers: {
              authorization: `Bearer ${token}`,
              "content-type": "application/json",
              "x-next-trainer-session-id": sessionId,
              "x-next-trainer-tool-call-id": toolCallId,
            },
            body: JSON.stringify({ arguments: params }),
            ...(signal ? { signal } : {}),
          },
        );
        if (!result.ok) {
          throw new Error("The Host Tool reported a failure.");
        }
        const text = typeof result.data === "string" ? result.data : JSON.stringify(result.data ?? null);
        return {
          content: [{ type: "text", text }],
          details: { auditId: result.audit_id ?? null, hostDetails: result.details ?? null },
        };
      },
    });
    registered += 1;
  }
  warn(`registered ${registered}/${catalog.length} host tools.`);
}

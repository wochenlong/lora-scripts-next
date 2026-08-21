import type {
  AgentEvent,
  AgentEventListener,
  AgentMessage,
  AgentTransport,
  CompactResult,
  CreateSessionInput,
  HistoryOptions,
  ModelSelection,
  PromptInput,
  PromptReceipt,
  ProviderProfile,
  ProviderStatus,
  ProviderTestResult,
  QueuedMessages,
  SaveProviderKeyInput,
  SessionHistory,
  SessionState,
  SessionSummary,
  ThinkingLevel,
  Unsubscribe,
} from "../contracts/agent-transport.ts";

interface MemorySession {
  state: SessionState;
  createdAt: string;
  updatedAt: string;
  messages: AgentMessage[];
  thinking: Map<string, string>;
}

interface MemoryProvider {
  profile: ProviderProfile;
  key?: string;
  lastTest?: ProviderTestResult;
}

function identifier(prefix: string): string {
  const suffix = typeof globalThis.crypto?.randomUUID === "function"
    ? globalThis.crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}-${suffix}`;
}

function copyQueue(queue: QueuedMessages): QueuedMessages {
  return { steering: [...queue.steering], followUp: [...queue.followUp] };
}

function copyState(state: SessionState): SessionState {
  return {
    ...state,
    model: state.model ? { ...state.model } : null,
    queue: copyQueue(state.queue),
    contextUsage: state.contextUsage ? { ...state.contextUsage } : state.contextUsage,
  };
}

function copyMessage(message: AgentMessage): AgentMessage {
  return structuredClone(message);
}

export class MemoryTransport implements AgentTransport {
  private readonly sessionRecords = new Map<string, MemorySession>();
  private readonly providerRecords = new Map<string, MemoryProvider>();
  private readonly listeners = new Map<string, Set<AgentEventListener>>();
  readonly operations: string[] = [];

  readonly sessions = {
    list: async (): Promise<SessionSummary[]> => {
      this.operations.push("sessions.list");
      return [...this.sessionRecords.values()]
        .map((record) => ({
          id: record.state.id,
          name: record.state.name,
          createdAt: record.createdAt,
          updatedAt: record.updatedAt,
          messageCount: record.messages.length,
          running: record.state.status === "running" || record.state.status === "cancelling",
          model: record.state.model ? { ...record.state.model } : null,
        }))
        .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
    },

    create: async (input: CreateSessionInput): Promise<SessionState> => {
      this.operations.push("sessions.create");
      const id = identifier("session");
      const now = new Date().toISOString();
      const state: SessionState = {
        id,
        name: input.name,
        runId: 0,
        status: "idle",
        model: input.model ? { ...input.model } : null,
        thinkingLevel: input.thinkingLevel ?? "auto",
        queue: { steering: [], followUp: [] },
      };
      this.sessionRecords.set(id, {
        state,
        createdAt: now,
        updatedAt: now,
        messages: [],
        thinking: new Map(),
      });
      return copyState(state);
    },

    rename: async (sessionId: string, name: string): Promise<void> => {
      this.operations.push("sessions.rename");
      const record = this.requireSession(sessionId);
      record.state.name = name;
      record.updatedAt = new Date().toISOString();
    },

    delete: async (sessionId: string): Promise<void> => {
      this.operations.push("sessions.delete");
      this.requireSession(sessionId);
      this.sessionRecords.delete(sessionId);
      this.listeners.delete(sessionId);
    },

    getState: async (sessionId: string): Promise<SessionState> => {
      this.operations.push("sessions.getState");
      return copyState(this.requireSession(sessionId).state);
    },

    getHistory: async (sessionId: string, options: HistoryOptions = {}): Promise<SessionHistory> => {
      this.operations.push("sessions.getHistory");
      const record = this.requireSession(sessionId);
      const limit = Math.max(1, options.limit ?? (record.messages.length || 1));
      const offset = Math.max(0, Number.parseInt(options.cursor ?? "0", 10) || 0);
      const slice = record.messages.slice(offset, offset + limit).map(copyMessage);
      const nextOffset = offset + slice.length;
      return {
        session: copyState(record.state),
        messages: slice,
        hasMore: nextOffset < record.messages.length,
        ...(nextOffset < record.messages.length ? { cursor: String(nextOffset) } : {}),
      };
    },

    getThinking: async (sessionId: string, entryId: string, blockIndex: number): Promise<string> => {
      this.operations.push("sessions.getThinking");
      const value = this.requireSession(sessionId).thinking.get(`${entryId}:${blockIndex}`);
      if (value === undefined) throw new Error("Thinking content is unavailable");
      return value;
    },

    prompt: async (sessionId: string, input: PromptInput): Promise<PromptReceipt> => {
      this.operations.push("sessions.prompt");
      const record = this.requireSession(sessionId);
      if (record.state.status === "running") {
        if (!input.streamingBehavior) {
          return {
            accepted: false,
            sessionId,
            runId: record.state.runId,
            clientSubmissionId: input.clientSubmissionId,
            code: "PROMPT_REJECTED",
          };
        }
        const queue = input.streamingBehavior === "steer"
          ? record.state.queue.steering
          : record.state.queue.followUp;
        queue.push(input.text);
        record.updatedAt = new Date().toISOString();
        return {
          accepted: true,
          sessionId,
          runId: record.state.runId,
          clientSubmissionId: input.clientSubmissionId,
          disposition: "queued",
        };
      }

      record.state.runId += 1;
      record.state.status = "running";
      record.messages.push({
        role: "user",
        id: input.clientSubmissionId,
        content: [
          { type: "text", text: input.text },
          ...(input.images ?? []).map((image) => ({
            type: "image" as const,
            data: image.data,
            mimeType: image.mimeType,
            alt: image.name,
          })),
        ],
        timestamp: Date.now(),
      });
      record.updatedAt = new Date().toISOString();
      return {
        accepted: true,
        sessionId,
        runId: record.state.runId,
        clientSubmissionId: input.clientSubmissionId,
        disposition: "started",
      };
    },

    cancel: async (sessionId: string): Promise<void> => {
      this.operations.push("sessions.cancel");
      const record = this.requireSession(sessionId);
      if (record.state.status === "running") record.state.status = "cancelling";
    },

    compact: async (sessionId: string, _instructions?: string): Promise<CompactResult> => {
      this.operations.push("sessions.compact");
      const record = this.requireSession(sessionId);
      return {
        tokensBefore: record.messages.length * 100,
        estimatedTokensAfter: record.messages.length * 40,
      };
    },

    setModel: async (sessionId: string, model: ModelSelection): Promise<void> => {
      this.operations.push("sessions.setModel");
      this.requireSession(sessionId).state.model = { ...model };
    },

    setThinkingLevel: async (sessionId: string, level: ThinkingLevel): Promise<void> => {
      this.operations.push("sessions.setThinkingLevel");
      this.requireSession(sessionId).state.thinkingLevel = level;
    },

    recallQueue: async (sessionId: string): Promise<QueuedMessages> => {
      this.operations.push("sessions.recallQueue");
      const record = this.requireSession(sessionId);
      const recalled = copyQueue(record.state.queue);
      record.state.queue = { steering: [], followUp: [] };
      return recalled;
    },

    subscribe: (sessionId: string, listener: AgentEventListener): Unsubscribe => {
      this.operations.push("sessions.subscribe");
      this.requireSession(sessionId);
      const listeners = this.listeners.get(sessionId) ?? new Set<AgentEventListener>();
      listeners.add(listener);
      this.listeners.set(sessionId, listeners);
      return () => {
        listeners.delete(listener);
        if (listeners.size === 0) this.listeners.delete(sessionId);
      };
    },
  };

  readonly providers = {
    list: async (): Promise<ProviderProfile[]> => {
      this.operations.push("providers.list");
      return [...this.providerRecords.values()].map(({ profile }) => ({ ...profile }));
    },

    status: async (providerId: string): Promise<ProviderStatus> => {
      this.operations.push("providers.status");
      return this.publicProviderStatus(providerId);
    },

    saveKey: async (input: SaveProviderKeyInput): Promise<ProviderStatus> => {
      this.operations.push("providers.saveKey");
      const fingerprint = input.key.length <= 4 ? "configured" : `••••${input.key.slice(-4)}`;
      this.providerRecords.set(input.id, {
        key: input.key,
        profile: {
          id: input.id,
          label: input.id,
          endpoint: input.endpoint,
          modelId: input.modelId,
          configured: true,
          fingerprint,
          capabilities: ["text"],
        },
      });
      return this.publicProviderStatus(input.id);
    },

    removeKey: async (providerId: string): Promise<ProviderStatus> => {
      this.operations.push("providers.removeKey");
      const record = this.requireProvider(providerId);
      record.key = undefined;
      record.profile.configured = false;
      record.profile.fingerprint = undefined;
      return this.publicProviderStatus(providerId);
    },

    test: async (providerId: string): Promise<ProviderTestResult> => {
      this.operations.push("providers.test");
      const record = this.requireProvider(providerId);
      const result: ProviderTestResult = record.key
        ? { ok: true, status: 200, latencyMs: 1, responseText: "ok", stopReason: "stop" }
        : { ok: false, error: "Provider is not configured" };
      record.lastTest = result;
      return { ...result };
    },
  };

  emit(event: AgentEvent): void {
    const record = this.requireSession(event.sessionId);
    if (event.runId < record.state.runId) return;
    record.state.runId = event.runId;
    if (event.type === "prompt_done" || event.type === "agent_settled" || event.type === "cancelled") {
      record.state.status = "idle";
    } else if (event.type === "startup_error") {
      record.state.status = "failed";
    } else if (event.type === "connected" || event.type === "state_snapshot") {
      record.state = copyState(event.state);
    } else if (event.type === "message_end") {
      record.messages = record.messages.filter((message) => message.id !== event.message.id);
      record.messages.push(copyMessage(event.message));
    } else if (event.type === "tool_execution_end") {
      record.messages.push(copyMessage(event.result));
    } else if (event.type === "queue_update") {
      record.state.queue = copyQueue(event.queue);
    }
    for (const listener of this.listeners.get(event.sessionId) ?? []) listener(structuredClone(event));
  }

  setThinking(sessionId: string, entryId: string, blockIndex: number, content: string): void {
    this.requireSession(sessionId).thinking.set(`${entryId}:${blockIndex}`, content);
  }

  seedProvider(profile: ProviderProfile): void {
    this.providerRecords.set(profile.id, { profile: { ...profile } });
  }

  private requireSession(sessionId: string): MemorySession {
    const record = this.sessionRecords.get(sessionId);
    if (!record) throw new Error(`Unknown session: ${sessionId}`);
    return record;
  }

  private requireProvider(providerId: string): MemoryProvider {
    const record = this.providerRecords.get(providerId);
    if (!record) throw new Error(`Unknown provider: ${providerId}`);
    return record;
  }

  private publicProviderStatus(providerId: string): ProviderStatus {
    const record = this.requireProvider(providerId);
    return {
      id: providerId,
      configured: record.profile.configured,
      fingerprint: record.profile.fingerprint,
      lastTest: record.lastTest ? { ...record.lastTest } : undefined,
    };
  }
}

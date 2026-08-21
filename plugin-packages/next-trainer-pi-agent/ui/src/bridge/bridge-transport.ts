import type {
  AgentEventListener,
  AgentTransport,
  CreateSessionInput,
  HistoryOptions,
  ModelSelection,
  PromptInput,
  SaveProviderKeyInput,
  ThinkingLevel,
  Unsubscribe,
} from "../contracts/agent-transport.ts";
import type {
  ArtifactReference,
  ConfirmationRequest,
  HostCapabilities,
  ResourceSelection,
  ThemeTokens,
} from "../contracts/host-capabilities.ts";
import { PluginBridgeClient } from "./plugin-bridge-client.ts";

function definedRecord(input: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(input).filter(([, value]) => value !== undefined));
}

export class BridgeAgentTransport implements AgentTransport {
  private readonly bridge: PluginBridgeClient;
  private readonly listeners = new Map<string, Set<AgentEventListener>>();
  private readonly unsubscribeEvents: () => void;

  constructor(bridge: PluginBridgeClient) {
    this.bridge = bridge;
    this.unsubscribeEvents = bridge.onEvent((event) => {
      for (const listener of this.listeners.get(event.sessionId) ?? []) listener(event);
    });
  }

  readonly sessions: AgentTransport["sessions"] = {
    list: () => this.bridge.request("session.list", {}),
    create: (input: CreateSessionInput) => this.bridge.request("session.create", definedRecord({
      name: input.name,
      model: input.model,
      thinkingLevel: input.thinkingLevel,
    })),
    rename: (sessionId: string, name: string) => this.bridge.request("session.rename", { sessionId, name }),
    delete: (sessionId: string) => this.bridge.request("session.delete", { sessionId }),
    getState: (sessionId: string) => this.bridge.request("session.getState", { sessionId }),
    getHistory: (sessionId: string, options: HistoryOptions = {}) => this.bridge.request("session.getHistory", definedRecord({
      sessionId,
      cursor: options.cursor,
      limit: options.limit,
      deferThinking: options.deferThinking,
      deferMedia: options.deferMedia,
    })),
    getThinking: (sessionId: string, entryId: string, blockIndex: number) =>
      this.bridge.request("session.getThinking", { sessionId, entryId, blockIndex }),
    prompt: (sessionId: string, input: PromptInput) => this.bridge.request("session.prompt", { sessionId, input }),
    cancel: (sessionId: string) => this.bridge.request("session.cancel", { sessionId }),
    compact: (sessionId: string, instructions?: string) =>
      this.bridge.request("session.compact", definedRecord({ sessionId, instructions })),
    setModel: (sessionId: string, model: ModelSelection) =>
      this.bridge.request("session.setModel", { sessionId, model }),
    setThinkingLevel: (sessionId: string, level: ThinkingLevel) =>
      this.bridge.request("session.setThinkingLevel", { sessionId, level }),
    recallQueue: (sessionId: string) => this.bridge.request("session.recallQueue", { sessionId }),
    subscribe: (sessionId: string, listener: AgentEventListener): Unsubscribe => {
      const listeners = this.listeners.get(sessionId) ?? new Set<AgentEventListener>();
      const first = listeners.size === 0;
      listeners.add(listener);
      this.listeners.set(sessionId, listeners);
      if (first) void this.bridge.request("session.subscribe", { sessionId }).catch(() => undefined);
      return () => {
        listeners.delete(listener);
        if (listeners.size === 0) this.listeners.delete(sessionId);
      };
    },
  };

  readonly providers: AgentTransport["providers"] = {
    list: () => this.bridge.request("provider.list", {}),
    status: (providerId: string) => this.bridge.request("provider.status", { profileId: providerId }),
    saveKey: (input: SaveProviderKeyInput) => this.bridge.request("provider.saveKey", {
      profileId: input.id,
      endpoint: input.endpoint,
      modelId: input.modelId,
      key: input.key,
    }),
    removeKey: (providerId: string) => this.bridge.request("provider.removeKey", { profileId: providerId }),
    test: (providerId: string) => this.bridge.request("provider.test", { profileId: providerId }),
  };

  dispose(): void {
    this.listeners.clear();
    this.unsubscribeEvents();
  }
}

export class BridgeHostCapabilities implements HostCapabilities {
  private readonly bridge: PluginBridgeClient;
  private readonly locale: string;
  private readonly initialTheme: ThemeTokens;

  constructor(
    bridge: PluginBridgeClient,
    locale: string,
    initialTheme: ThemeTokens,
  ) {
    this.bridge = bridge;
    this.locale = locale;
    this.initialTheme = initialTheme;
  }

  readonly environment: HostCapabilities["environment"] = {
    getContext: async () => {
      const context = await this.bridge.request<Record<string, unknown>>("context.get", {});
      return {
        route: String(context.route ?? ""),
        locale: this.locale,
        colorScheme: context.colorScheme === "dark" ? "dark" : "light",
        ...(typeof context.activeTrainingId === "string" ? { activeTrainingId: context.activeTrainingId } : {}),
        ...(typeof context.activeDatasetId === "string" ? { activeDatasetId: context.activeDatasetId } : {}),
      };
    },
    getTheme: async () => {
      const result = await this.bridge.request<ThemeTokens | { tokens: ThemeTokens }>("theme.get", {});
      return "tokens" in result ? result.tokens : result;
    },
  };

  readonly resources: HostCapabilities["resources"] = {
    pick: (kinds: ResourceSelection["kind"][]) => this.bridge.request("resource.pick", { kinds }),
    getSummary: (resourceId: string) => this.bridge.request("resource.getSummary", { resourceId }),
  };

  readonly confirmations: HostCapabilities["confirmations"] = {
    request: (input: ConfirmationRequest) => this.bridge.request("confirmation.request", { ...input }),
    getResult: (ticketId: string) => this.bridge.request("confirmation.getResult", { ticketId }),
  };

  readonly artifacts: HostCapabilities["artifacts"] = {
    open: (reference: ArtifactReference) => this.bridge.request("artifact.open", { ...reference }),
    download: (reference: ArtifactReference) => this.bridge.request("artifact.download", { ...reference }),
  };

  readonly navigation: HostCapabilities["navigation"] = {
    openExternal: (url: string) => this.bridge.request("navigation.openExternal", { url }),
    openPluginRoute: (route: string) => this.bridge.request("navigation.openPluginRoute", { route }),
  };

  get fallbackTheme(): ThemeTokens {
    return this.initialTheme;
  }
}

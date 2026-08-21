/*
 * Derived from the session and provider behavior of agegr/pi-web 0.8.9.
 * Upstream commit: 2a6e53710f6409e0cceb3de839a62f8cdf3ca3ca (MIT).
 * This file defines the product-owned transport boundary; it contains no I/O.
 */

export type SessionId = string;
export type RunId = number;
export type ThinkingLevel = "auto" | "off" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max";

export interface ModelSelection {
  profileId: string;
  modelId: string;
}

export interface ImageAttachment {
  data: string;
  mimeType: string;
  name?: string;
}

export interface TextBlock {
  type: "text";
  text: string;
}

export interface ImageBlock {
  type: "image";
  data: string;
  mimeType: string;
  alt?: string;
}

export interface ThinkingBlock {
  type: "thinking";
  thinking: string;
  deferred?: boolean;
}

export interface ToolCallBlock {
  type: "toolCall";
  toolCallId: string;
  toolName: string;
  input?: unknown;
  rawInput?: string;
}

export type AssistantBlock = TextBlock | ImageBlock | ThinkingBlock | ToolCallBlock;

export interface UserMessage {
  role: "user";
  id: string;
  content: Array<TextBlock | ImageBlock>;
  timestamp?: number;
}

export interface AssistantMessage {
  role: "assistant";
  id: string;
  content: AssistantBlock[];
  stopReason?: string;
  errorMessage?: string;
  timestamp?: number;
  usage?: TokenUsage;
}

export interface ToolResultMessage {
  role: "toolResult";
  id: string;
  toolCallId: string;
  toolName: string;
  content: string;
  isError?: boolean;
  timestamp?: number;
}

export interface NoticeMessage {
  role: "notice";
  id: string;
  level: "info" | "success" | "warning" | "error";
  content: string;
  timestamp?: number;
}

export type AgentMessage = UserMessage | AssistantMessage | ToolResultMessage | NoticeMessage;

export interface TokenUsage {
  input?: number;
  output?: number;
  cacheRead?: number;
  cacheWrite?: number;
  total?: number;
}

export interface SessionSummary {
  id: SessionId;
  name?: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
  running: boolean;
  model?: ModelSelection | null;
}

export interface SessionState {
  id: SessionId;
  name?: string;
  runId: RunId;
  status: "idle" | "running" | "cancelling" | "failed";
  model: ModelSelection | null;
  thinkingLevel: ThinkingLevel;
  contextUsage?: { percent: number | null; contextWindow: number; tokens: number | null } | null;
  queue: QueuedMessages;
}

export interface SessionHistory {
  session: SessionState;
  messages: AgentMessage[];
  hasMore: boolean;
  cursor?: string;
}

export interface HistoryOptions {
  cursor?: string;
  limit?: number;
  deferThinking?: boolean;
  deferMedia?: boolean;
}

export interface CreateSessionInput {
  name?: string;
  model?: ModelSelection;
  thinkingLevel?: ThinkingLevel;
}

export interface PromptInput {
  text: string;
  images?: ImageAttachment[];
  streamingBehavior?: "steer" | "followUp";
  clientSubmissionId: string;
}

export interface PromptReceipt {
  accepted: boolean;
  sessionId: SessionId;
  runId: RunId;
  clientSubmissionId: string;
  disposition?: "started" | "queued";
  code?: string;
}

export class AgentTransportError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly accepted?: boolean,
  ) {
    super(message);
    this.name = "AgentTransportError";
  }
}

export interface CompactResult {
  tokensBefore: number;
  estimatedTokensAfter: number;
}

export interface QueuedMessages {
  steering: string[];
  followUp: string[];
}

export interface ProviderProfile {
  id: string;
  label: string;
  endpoint: string;
  modelId: string;
  configured: boolean;
  fingerprint?: string;
  capabilities?: Array<"text" | "image">;
  thinkingLevels?: ThinkingLevel[];
}

export interface ProviderStatus {
  id: string;
  configured: boolean;
  fingerprint?: string;
  lastTest?: ProviderTestResult;
}

export interface SaveProviderKeyInput {
  id: string;
  endpoint: string;
  modelId: string;
  key: string;
}

export interface ProviderTestResult {
  ok: boolean;
  status?: number;
  latencyMs?: number;
  responseText?: string;
  stopReason?: string;
  error?: string;
}

export type AssistantMessageEvent =
  | { type: "text_start"; contentIndex: number }
  | { type: "text_delta"; contentIndex: number; delta: string }
  | { type: "text_end"; contentIndex: number }
  | { type: "thinking_start"; contentIndex: number }
  | { type: "thinking_delta"; contentIndex: number; delta: string }
  | { type: "thinking_end"; contentIndex: number }
  | { type: "toolcall_start"; contentIndex: number; id: string; toolName: string }
  | { type: "toolcall_delta"; contentIndex: number; id: string; toolName: string; delta: string }
  | { type: "toolcall_end"; contentIndex: number; id: string; toolName: string };

interface EventBase {
  eventId: string;
  sessionId: SessionId;
  runId: RunId;
}

export type AgentEvent =
  | (EventBase & { type: "connected"; state: SessionState; snapshot?: AssistantMessage | null })
  | (EventBase & { type: "state_snapshot"; state: SessionState; snapshot?: AssistantMessage | null })
  | (EventBase & { type: "message_start"; message: AssistantMessage })
  | (EventBase & { type: "message_update"; assistantMessageEvent: AssistantMessageEvent })
  | (EventBase & { type: "message_end"; message: AssistantMessage })
  | (EventBase & { type: "tool_execution_start"; toolCallId: string; toolName: string })
  | (EventBase & { type: "tool_execution_update"; toolCallId: string; toolName: string; progress?: string })
  | (EventBase & { type: "tool_execution_end"; toolCallId: string; toolName: string; result: ToolResultMessage })
  | (EventBase & { type: "queue_update"; queue: QueuedMessages })
  | (EventBase & { type: "usage"; usage: TokenUsage })
  | (EventBase & { type: "agent_end" })
  | (EventBase & { type: "prompt_done" })
  | (EventBase & { type: "agent_settled" })
  | (EventBase & { type: "cancelled" })
  | (EventBase & { type: "startup_error"; message: string });

export type AgentEventListener = (event: AgentEvent) => void;
export type Unsubscribe = () => void;

export interface SessionTransport {
  list(): Promise<SessionSummary[]>;
  create(input: CreateSessionInput): Promise<SessionState>;
  rename(sessionId: SessionId, name: string): Promise<void>;
  delete(sessionId: SessionId): Promise<void>;
  getState(sessionId: SessionId): Promise<SessionState>;
  getHistory(sessionId: SessionId, options?: HistoryOptions): Promise<SessionHistory>;
  getThinking(sessionId: SessionId, entryId: string, blockIndex: number): Promise<string>;
  prompt(sessionId: SessionId, input: PromptInput): Promise<PromptReceipt>;
  cancel(sessionId: SessionId): Promise<void>;
  compact(sessionId: SessionId, instructions?: string): Promise<CompactResult>;
  setModel(sessionId: SessionId, model: ModelSelection): Promise<void>;
  setThinkingLevel(sessionId: SessionId, level: ThinkingLevel): Promise<void>;
  recallQueue(sessionId: SessionId): Promise<QueuedMessages>;
  subscribe(sessionId: SessionId, listener: AgentEventListener): Unsubscribe;
}

export interface ProviderTransport {
  list(): Promise<ProviderProfile[]>;
  status(providerId: string): Promise<ProviderStatus>;
  saveKey(input: SaveProviderKeyInput): Promise<ProviderStatus>;
  removeKey(providerId: string): Promise<ProviderStatus>;
  test(providerId: string): Promise<ProviderTestResult>;
}

export interface AgentTransport {
  readonly sessions: SessionTransport;
  readonly providers: ProviderTransport;
}

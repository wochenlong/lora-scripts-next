/* Streaming reducer behavior adapted from agegr/pi-web 0.8.9 (MIT). */

import type {
  AgentEvent,
  AgentMessage,
  AssistantBlock,
  AssistantMessage,
  AssistantMessageEvent,
  SessionHistory,
  SessionState,
  ToolResultMessage,
} from "../contracts/agent-transport.ts";
import {
  INITIAL_TERMINAL_STATE,
  reduceTerminalState,
  type TerminalState,
} from "./terminal-state.ts";

export interface RunningTool {
  id: string;
  name: string;
  progress?: string;
}

export interface ConversationState {
  session: SessionState | null;
  messages: AgentMessage[];
  terminal: TerminalState;
  runningTools: RunningTool[];
  usage: { input?: number; output?: number; cacheRead?: number; cacheWrite?: number; total?: number } | null;
  error: string | null;
}

export type ConversationAction =
  | { type: "history_loaded"; history: SessionHistory }
  | { type: "run_started"; session: SessionState; optimisticMessage: AgentMessage }
  | { type: "event"; event: AgentEvent }
  | { type: "operation_failed"; error: string };

export const INITIAL_CONVERSATION_STATE: ConversationState = {
  session: null,
  messages: [],
  terminal: INITIAL_TERMINAL_STATE,
  runningTools: [],
  usage: null,
  error: null,
};

function upsertMessage(messages: AgentMessage[], message: AgentMessage): AgentMessage[] {
  const index = messages.findIndex((candidate) => candidate.id === message.id);
  if (index < 0) return [...messages, message];
  return messages.map((candidate, candidateIndex) => candidateIndex === index ? message : candidate);
}

function latestAssistant(messages: AgentMessage[]): { index: number; message: AssistantMessage } | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role === "assistant") return { index, message };
  }
  return null;
}

function ensureBlock(blocks: AssistantBlock[], event: AssistantMessageEvent): AssistantBlock[] {
  const result = [...blocks];
  const existing = result[event.contentIndex];
  if (event.type === "text_start" || event.type === "text_delta" || event.type === "text_end") {
    if (existing?.type !== "text") result[event.contentIndex] = { type: "text", text: "" };
  } else if (event.type === "thinking_start" || event.type === "thinking_delta" || event.type === "thinking_end") {
    if (existing?.type !== "thinking") result[event.contentIndex] = { type: "thinking", thinking: "" };
  } else {
    if (existing?.type !== "toolCall") {
      result[event.contentIndex] = {
        type: "toolCall",
        toolCallId: event.id,
        toolName: event.toolName,
        rawInput: "",
      };
    }
  }
  return result;
}

function applyAssistantUpdate(message: AssistantMessage, event: AssistantMessageEvent): AssistantMessage {
  const content = ensureBlock(message.content, event);
  const block = content[event.contentIndex];

  if (event.type === "text_delta" && block?.type === "text") {
    content[event.contentIndex] = { ...block, text: block.text + event.delta };
  } else if (event.type === "thinking_delta" && block?.type === "thinking") {
    content[event.contentIndex] = { ...block, thinking: block.thinking + event.delta };
  } else if (event.type === "toolcall_delta" && block?.type === "toolCall") {
    content[event.contentIndex] = {
      ...block,
      toolCallId: event.id,
      toolName: event.toolName,
      rawInput: `${block.rawInput ?? ""}${event.delta}`,
    };
  }

  return { ...message, content };
}

function replaceLatestAssistant(messages: AgentMessage[], update: AssistantMessageEvent): AgentMessage[] {
  const latest = latestAssistant(messages);
  if (!latest) return messages;
  const next = [...messages];
  next[latest.index] = applyAssistantUpdate(latest.message, update);
  return next;
}

function appendToolResult(messages: AgentMessage[], result: ToolResultMessage): AgentMessage[] {
  return upsertMessage(messages, result);
}

function reduceEvent(state: ConversationState, event: AgentEvent): ConversationState {
  if (event.runId < state.terminal.runId) return state;

  const terminal = reduceTerminalState(state.terminal, event);
  let session = state.session;
  let messages = state.messages;
  let runningTools = state.runningTools;
  let usage = state.usage;
  let error = state.error;

  if (event.type === "connected" || event.type === "state_snapshot") {
    session = event.state;
    if (event.snapshot) messages = upsertMessage(messages, event.snapshot);
  } else if (event.type === "message_start") {
    messages = upsertMessage(messages, event.message);
  } else if (event.type === "message_update") {
    messages = replaceLatestAssistant(messages, event.assistantMessageEvent);
  } else if (event.type === "message_end") {
    messages = upsertMessage(messages, event.message);
    if (event.message.stopReason === "error" || event.message.stopReason === "aborted") {
      error = event.message.errorMessage ?? `Model stopped with ${event.message.stopReason}`;
    }
  } else if (event.type === "tool_execution_start") {
    runningTools = [
      ...runningTools.filter((tool) => tool.id !== event.toolCallId),
      { id: event.toolCallId, name: event.toolName },
    ];
  } else if (event.type === "tool_execution_update") {
    runningTools = runningTools.map((tool) => tool.id === event.toolCallId
      ? { ...tool, progress: event.progress }
      : tool);
  } else if (event.type === "tool_execution_end") {
    runningTools = runningTools.filter((tool) => tool.id !== event.toolCallId);
    messages = appendToolResult(messages, event.result);
  } else if (event.type === "queue_update" && session) {
    session = { ...session, queue: event.queue };
  } else if (event.type === "usage") {
    usage = event.usage;
  } else if (event.type === "startup_error") {
    error = event.message;
  }

  if (session && terminal.runId >= session.runId) {
    session = {
      ...session,
      runId: terminal.runId,
      status: terminal.phase === "terminal"
        ? (terminal.outcome === "failed" ? "failed" : "idle")
        : (terminal.phase === "idle" ? "idle" : "running"),
    };
  }

  return { session, messages, terminal, runningTools, usage, error };
}

export function conversationReducer(
  state: ConversationState,
  action: ConversationAction,
): ConversationState {
  switch (action.type) {
    case "history_loaded":
      return {
        ...state,
        session: action.history.session,
        messages: action.history.messages,
        terminal: action.history.session.status === "failed"
          ? {
              runId: action.history.session.runId,
              phase: "terminal",
              outcome: "failed",
              sawAgentEnd: false,
            }
          : {
              runId: action.history.session.runId,
              phase: action.history.session.status === "running" ? "running" : "idle",
              outcome: null,
              sawAgentEnd: false,
            },
        error: null,
      };
    case "run_started":
      return {
        ...state,
        session: action.session,
        messages: upsertMessage(state.messages, action.optimisticMessage),
        terminal: {
          runId: action.session.runId,
          phase: "running",
          outcome: null,
          sawAgentEnd: false,
        },
        error: null,
      };
    case "event":
      return reduceEvent(state, action.event);
    case "operation_failed":
      return { ...state, error: action.error };
    default:
      return state;
  }
}

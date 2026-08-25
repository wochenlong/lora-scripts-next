import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import type {
  AgentTransport,
  AgentMessage,
  ModelSelection,
  PromptInput,
  PromptReceipt,
  SessionState,
  Unsubscribe,
} from "../contracts/agent-transport.ts";
import {
  conversationReducer,
  INITIAL_CONVERSATION_STATE,
} from "../events/conversation-reducer.ts";

function identifier(prefix: string): string {
  const suffix = typeof globalThis.crypto?.randomUUID === "function"
    ? globalThis.crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}-${suffix}`;
}

function errorCode(error: unknown): string {
  if (!(error instanceof Error)) return "";
  const candidate = error as Error & { code?: unknown };
  return typeof candidate.code === "string" ? candidate.code : "";
}

export interface UseAgentConversationOptions {
  transport: AgentTransport;
  initialSessionId?: string | null;
  initialModel?: ModelSelection;
}

export function useAgentConversation({
  transport,
  initialSessionId = null,
  initialModel,
}: UseAgentConversationOptions) {
  const [state, dispatch] = useReducer(conversationReducer, INITIAL_CONVERSATION_STATE);
  const [ready, setReady] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(initialSessionId);
  const sessionIdRef = useRef<string | null>(initialSessionId);
  const subscriptionRef = useRef<Unsubscribe | null>(null);
  const subscriptionSessionRef = useRef<string | null>(null);

  const attach = useCallback((sessionId: string) => {
    if (subscriptionSessionRef.current === sessionId && subscriptionRef.current) return;
    subscriptionRef.current?.();
    subscriptionSessionRef.current = sessionId;
    subscriptionRef.current = transport.sessions.subscribe(sessionId, (event) => {
      dispatch({ type: "event", event });
    });
  }, [transport]);

  useEffect(() => {
    let active = true;
    const sessionId = initialSessionId;
    sessionIdRef.current = sessionId;
    setSessionId(sessionId);
    setReady(false);
    dispatch({ type: "session_cleared" });
    if (!sessionId) {
      subscriptionRef.current?.();
      subscriptionRef.current = null;
      subscriptionSessionRef.current = null;
      setReady(true);
      return () => { active = false; };
    }

    // Establish event delivery before reading history or accepting a prompt.
    attach(sessionId);
    void transport.sessions.getHistory(sessionId, {
      limit: 200,
      deferThinking: true,
      deferMedia: true,
    }).then((history) => {
      if (!active || sessionIdRef.current !== sessionId) return;
      dispatch({ type: "history_loaded", history });
      setReady(true);
    }).catch((error: unknown) => {
      if (!active) return;
      dispatch({ type: "operation_failed", error: error instanceof Error ? error.message : String(error) });
      setReady(true);
    });

    return () => {
      active = false;
      if (subscriptionSessionRef.current === sessionId) {
        subscriptionRef.current?.();
        subscriptionRef.current = null;
        subscriptionSessionRef.current = null;
      }
    };
  }, [attach, initialSessionId, transport]);

  useEffect(() => {
    const activeSessionId = sessionId;
    if (!activeSessionId || (state.terminal.phase !== "running" && state.terminal.phase !== "settling")) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let inFlight = false;

    const reconcile = async () => {
      if (!active || inFlight) return;
      inFlight = true;
      try {
        const authoritative = await transport.sessions.getState(activeSessionId);
        if (!active) return;
        if (authoritative.status === "idle" || authoritative.status === "failed") {
          try {
            const history = await transport.sessions.getHistory(activeSessionId, {
              limit: 200,
              deferThinking: true,
              deferMedia: true,
            });
            if (active) dispatch({ type: "history_loaded", history });
          } catch {
            if (active) dispatch({ type: "session_reconciled", session: authoritative });
          }
          return;
        }
      } catch {
        // The authenticated event stream remains the primary channel. A
        // transient reconciliation read failure must not replace its state.
      } finally {
        inFlight = false;
      }
      if (active) timer = setTimeout(() => void reconcile(), 500);
    };

    timer = setTimeout(() => void reconcile(), 500);
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [sessionId, state.terminal.phase, transport]);

  const ensureSession = useCallback(async (): Promise<SessionState> => {
    const existingId = sessionIdRef.current;
    if (existingId) {
      attach(existingId);
      return transport.sessions.getState(existingId);
    }
    const created = await transport.sessions.create({ model: initialModel, thinkingLevel: "auto" });
    sessionIdRef.current = created.id;
    setSessionId(created.id);
    // The subscription is deliberately attached before the first prompt.
    attach(created.id);
    return created;
  }, [attach, initialModel, transport]);

  const send = useCallback(async (
    text: string,
    streamingBehavior?: PromptInput["streamingBehavior"],
  ): Promise<PromptReceipt> => {
    const trimmed = text.trim();
    if (!trimmed) throw new Error("Prompt is empty");
    const session = await ensureSession();
    dispatch({ type: "session_reconciled", session });
    const clientSubmissionId = identifier("submission");
    const sessionIsRunning = session.status === "running" || session.status === "cancelling";
    const effectiveStreamingBehavior = sessionIsRunning ? streamingBehavior : undefined;
    const input: PromptInput = { text: trimmed, clientSubmissionId, streamingBehavior: effectiveStreamingBehavior };
    let receipt: PromptReceipt;
    try {
      receipt = await transport.sessions.prompt(session.id, input);
    } catch (error) {
      // The run can settle between the authoritative getState above and the
      // prompt request. A rejected follow-up was never admitted, so retrying
      // the same client submission once as a normal prompt is safe.
      if (!effectiveStreamingBehavior || errorCode(error) !== "SESSION_NOT_RUNNING") throw error;
      const reconciled = await transport.sessions.getState(session.id);
      dispatch({ type: "session_reconciled", session: reconciled });
      if (reconciled.status !== "idle") throw error;
      receipt = await transport.sessions.prompt(session.id, {
        text: trimmed,
        clientSubmissionId,
      });
    }
    if (!receipt.accepted) return receipt;

    if (receipt.disposition === "queued") return receipt;

    const optimisticMessage: AgentMessage = {
      role: "user",
      id: clientSubmissionId,
      content: [{ type: "text", text: trimmed }],
      timestamp: Date.now(),
    };
    dispatch({
      type: "run_started",
      session: { ...session, runId: receipt.runId, status: "running" },
      optimisticMessage,
    });
    return receipt;
  }, [ensureSession, transport]);

  const cancel = useCallback(async () => {
    const sessionId = sessionIdRef.current;
    if (sessionId) await transport.sessions.cancel(sessionId);
  }, [transport]);

  return {
    state,
    ready,
    sessionId,
    send,
    cancel,
  };
}

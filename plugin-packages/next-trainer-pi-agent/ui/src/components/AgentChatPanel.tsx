import { useEffect, useMemo, useState, type KeyboardEvent } from "react";

import type {
  AgentMessage,
  AgentTransport,
  AssistantMessage,
  ToolResultMessage,
  SessionSummary,
} from "../contracts/agent-transport.ts";
import type { HostCapabilities } from "../contracts/host-capabilities.ts";
import { useAgentConversation } from "../hooks/useAgentConversation.ts";
import { useI18n } from "../i18n/I18nProvider.tsx";
import { SafeMarkdown } from "../rendering/SafeMarkdown.tsx";
import { isTerminal } from "../events/terminal-state.ts";
import "./agent-chat-panel.css";

export interface AgentChatPanelProps {
  transport: AgentTransport;
  host: HostCapabilities;
  initialSessionId?: string | null;
  modelLabel?: string;
}

function textContent(message: AgentMessage): string {
  if (message.role === "toolResult" || message.role === "notice") return message.content;
  return message.content
    .map((block) => block.type === "text" ? block.text : "")
    .filter(Boolean)
    .join("\n");
}

function AssistantCard({ message, host }: { message: AssistantMessage; host: HostCapabilities }) {
  const { t } = useI18n();
  return (
    <article className="nta-message nta-message-assistant" data-message-id={message.id}>
      {message.content.map((block, index) => {
        if (block.type === "text") {
          return <SafeMarkdown key={index} host={host}>{block.text}</SafeMarkdown>;
        }
        if (block.type === "thinking") {
          return (
            <details key={index} className="nta-thinking">
              <summary>{t("thinking")}</summary>
              {block.deferred
                ? <span className="nta-muted">…</span>
                : <SafeMarkdown host={host}>{block.thinking}</SafeMarkdown>}
            </details>
          );
        }
        if (block.type === "toolCall") {
          return (
            <section key={block.toolCallId} className="nta-tool-card">
              <strong>{block.toolName}</strong>
              {block.rawInput && <pre>{block.rawInput}</pre>}
            </section>
          );
        }
        const source = `data:${block.mimeType};base64,${block.data}`;
        return <img key={index} className="nta-message-image" src={source} alt={block.alt ?? ""} />;
      })}
      {message.errorMessage && <p className="nta-error" role="alert">{message.errorMessage}</p>}
    </article>
  );
}

function MessageCard({ message, host }: { message: AgentMessage; host: HostCapabilities }) {
  if (message.role === "assistant") return <AssistantCard message={message} host={host} />;
  if (message.role === "toolResult") {
    const result = message as ToolResultMessage;
    return (
      <article className={`nta-message nta-tool-result${result.isError ? " is-error" : ""}`}>
        <strong>{result.toolName}</strong>
        <SafeMarkdown host={host}>{result.content}</SafeMarkdown>
      </article>
    );
  }
  if (message.role === "notice") {
    return <p className={`nta-notice nta-notice-${message.level}`}>{message.content}</p>;
  }
  return <article className="nta-message nta-message-user">{textContent(message)}</article>;
}

function sessionDisplayName(session: SessionSummary, fallback: string): string {
  return session.name?.trim() || fallback;
}

function SessionHistoryDrawer({
  transport,
  currentSessionId,
  onSelect,
  onClose,
}: {
  transport: AgentTransport;
  currentSessionId: string | null;
  onSelect: (sessionId: string | null) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const refresh = async () => {
    try {
      setSessions(await transport.sessions.list());
      setError("");
    } catch {
      setError(t("sessionHistoryFailed"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, [transport]);

  const createSession = async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const created = await transport.sessions.create({ thinkingLevel: "auto" });
      onSelect(created.id);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("sessionHistoryFailed"));
    } finally {
      setBusy(false);
    }
  };

  const saveRename = async (session: SessionSummary) => {
    const value = renameValue.trim();
    if (!value || busy) return;
    setBusy(true);
    try {
      await transport.sessions.rename(session.id, value);
      setRenamingId(null);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("sessionHistoryFailed"));
    } finally {
      setBusy(false);
    }
  };

  const deleteSession = async (session: SessionSummary) => {
    if (busy) return;
    setBusy(true);
    try {
      await transport.sessions.delete(session.id);
      if (currentSessionId === session.id) onSelect(null);
      setDeleteId(null);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("sessionHistoryFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="nta-history-drawer" aria-label={t("history")}>
      <header className="nta-history-header">
        <strong>{t("history")}</strong>
        <div>
          <button type="button" disabled={busy} onClick={() => void createSession()}>{t("newSession")}</button>
          <button type="button" aria-label={t("closeHistory")} onClick={onClose}>×</button>
        </div>
      </header>
      <ul className="nta-history-list">
        {loading && <li className="nta-history-empty">…</li>}
        {!loading && sessions.length === 0 && <li className="nta-history-empty">{t("noSessions")}</li>}
        {sessions.map((session) => {
          const name = sessionDisplayName(session, t("untitledSession"));
          return (
            <li key={session.id} className={`nta-history-item${currentSessionId === session.id ? " is-active" : ""}`}>
              <div className="nta-history-summary">
                <strong>{name}</strong>
                <small>{new Date(session.updatedAt).toLocaleString()} · {session.messageCount}</small>
              </div>
              {renamingId === session.id ? (
                <div className="nta-history-rename">
                  <input
                    aria-label={t("sessionName")}
                    value={renameValue}
                    onChange={(event) => setRenameValue(event.target.value)}
                  />
                  <button
                    type="button"
                    aria-label={t("saveSessionName")}
                    disabled={busy || !renameValue.trim()}
                    onClick={() => void saveRename(session)}
                  >✓</button>
                  <button type="button" onClick={() => setRenamingId(null)}>{t("cancel")}</button>
                </div>
              ) : deleteId === session.id ? (
                <div className="nta-history-confirm">
                  <button
                    type="button"
                    aria-label={t("confirmDeleteSession", { name })}
                    disabled={busy}
                    onClick={() => void deleteSession(session)}
                  >{t("deleteSession", { name })}</button>
                  <button type="button" onClick={() => setDeleteId(null)}>{t("cancel")}</button>
                </div>
              ) : (
                <div className="nta-history-actions">
                  <button
                    type="button"
                    aria-label={t("resumeSession", { name })}
                    onClick={() => onSelect(session.id)}
                  >{t("resumeSession", { name })}</button>
                  <button
                    type="button"
                    aria-label={t("renameSession", { name })}
                    onClick={() => { setRenamingId(session.id); setRenameValue(name); }}
                  >{t("renameSession", { name })}</button>
                  <button
                    type="button"
                    aria-label={t("deleteSession", { name })}
                    onClick={() => setDeleteId(session.id)}
                  >{t("deleteSession", { name })}</button>
                </div>
              )}
            </li>
          );
        })}
        {error && <li className="nta-error" role="alert">{error}</li>}
      </ul>
    </aside>
  );
}

export function AgentChatPanel({
  transport,
  host,
  initialSessionId = null,
  modelLabel,
}: AgentChatPanelProps) {
  const { t } = useI18n();
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(initialSessionId);
  const [historyOpen, setHistoryOpen] = useState(false);
  const { state, ready, sessionId, send, cancel } = useAgentConversation({
    transport,
    initialSessionId: selectedSessionId,
  });
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const running = state.terminal.phase === "running" || state.terminal.phase === "settling";
  const queuedCount = (state.session?.queue.steering.length ?? 0) + (state.session?.queue.followUp.length ?? 0);
  const statusText = useMemo(() => {
    const latestTool = state.runningTools[state.runningTools.length - 1];
    if (latestTool) return t("toolRunning", { name: latestTool.name });
    if (!ready) return t("reconnecting");
    if (queuedCount > 0) return `${t("queued")} · ${queuedCount}`;
    return null;
  }, [queuedCount, ready, state.runningTools, t]);

  const submit = async () => {
    if (!draft.trim() || sending) return;
    const submitted = draft;
    setSending(true);
    setSubmitError("");
    try {
      const receipt = await send(submitted, running ? "followUp" : undefined);
      if (receipt.accepted) setDraft("");
    } catch (error) {
      // Preserve draft on a definitive admission failure and surface the
      // host/sidecar error (e.g. PROVIDER_NOT_CONFIGURED) to the user.
      console.error(error);
      const message = error instanceof Error ? error.message : String(error);
      const code = error instanceof Error && typeof (error as { code?: unknown }).code === "string"
        ? (error as { code?: string }).code
        : "";
      setSubmitError(code ? `${message} (${code})` : message);
    } finally {
      setSending(false);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    void submit();
  };

  return (
    <section
      className="nta-chat-panel"
      aria-label={t("assistant")}
      style={{ width: "100%", height: "100%" }}
    >
      <header className="nta-chat-header">
        <div><strong>{t("assistant")}</strong>{modelLabel && <span>{modelLabel}</span>}</div>
        <nav>
          <button type="button" onClick={() => setHistoryOpen(true)}>{t("history")}</button>
          <button
            type="button"
            onClick={() => void host.navigation.openPluginRoute("/settings/plugins/next-trainer-pi-agent")}
          >{t("providerSettings")}</button>
        </nav>
      </header>

      <div className="nta-message-list" role="log" aria-live="polite">
        {state.messages.length === 0 && <p className="nta-empty">{t("empty")}</p>}
        {state.messages.map((message) => <MessageCard key={message.id} message={message} host={host} />)}
        {statusText && <p className="nta-status">{statusText}</p>}
        {state.error && <p className="nta-error" role="alert">{state.error || t("error")}</p>}
      </div>

      {submitError && <p className="nta-error" role="alert">{submitError}</p>}
      <footer className="nta-composer">
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={t("inputPlaceholder")}
          rows={3}
        />
        {running && !isTerminal(state.terminal)
          ? <button type="button" className="nta-stop" onClick={() => void cancel()}>{t("stop")}</button>
          : <button type="button" className="nta-send" disabled={!ready || sending || !draft.trim()} onClick={() => void submit()}>{t("send")}</button>}
      </footer>
      {historyOpen && (
        <SessionHistoryDrawer
          transport={transport}
          currentSessionId={sessionId}
          onSelect={(nextSessionId) => { setSelectedSessionId(nextSessionId); setHistoryOpen(false); }}
          onClose={() => setHistoryOpen(false)}
        />
      )}
    </section>
  );
}

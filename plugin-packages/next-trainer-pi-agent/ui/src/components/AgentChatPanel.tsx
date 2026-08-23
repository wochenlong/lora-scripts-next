import { useMemo, useState, type KeyboardEvent } from "react";

import type {
  AgentMessage,
  AgentTransport,
  AssistantMessage,
  ToolResultMessage,
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

export function AgentChatPanel({
  transport,
  host,
  initialSessionId = null,
  modelLabel,
}: AgentChatPanelProps) {
  const { t } = useI18n();
  const { state, ready, send, cancel } = useAgentConversation({ transport, initialSessionId });
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
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
    try {
      const receipt = await send(submitted, running ? "followUp" : undefined);
      if (receipt.accepted) setDraft("");
    } catch (error) {
      // Preserve draft on a definitive admission failure.
      console.error(error);
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
      style={{ width: "520px", maxWidth: "100%", height: "680px", maxHeight: "100%" }}
    >
      <header className="nta-chat-header">
        <div><strong>{t("assistant")}</strong>{modelLabel && <span>{modelLabel}</span>}</div>
        <nav>
          <button type="button" onClick={() => void host.navigation.openPluginRoute("history")}>{t("history")}</button>
          <button type="button" onClick={() => void host.navigation.openPluginRoute("settings/provider")}>{t("providerSettings")}</button>
        </nav>
      </header>

      <div className="nta-message-list" role="log" aria-live="polite">
        {state.messages.length === 0 && <p className="nta-empty">{t("empty")}</p>}
        {state.messages.map((message) => <MessageCard key={message.id} message={message} host={host} />)}
        {statusText && <p className="nta-status">{statusText}</p>}
        {state.error && <p className="nta-error" role="alert">{state.error || t("error")}</p>}
      </div>

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
    </section>
  );
}



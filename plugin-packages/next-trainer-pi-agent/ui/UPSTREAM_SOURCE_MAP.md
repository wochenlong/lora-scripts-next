# pi-web slim UI source map

Upstream: `agegr/pi-web@0.8.9`, commit `2a6e53710f6409e0cceb3de839a62f8cdf3ca3ca`, MIT.

This directory is an independent React UI boundary. It retains selected interaction and event semantics but replaces the upstream server coupling with injected product contracts.

| Upstream source | Local destination | Mode | Retained behavior |
|---|---|---|---|
| `lib/types.ts` | `src/contracts/agent-transport.ts` | substantially modified | message, session, model and provider DTOs |
| `lib/agent-event-wire.ts` | `src/contracts/agent-transport.ts`, `src/events/conversation-reducer.ts` | behavior adaptation | projected assistant deltas and stable tool identity |
| `lib/streaming-message.ts` | `src/events/conversation-reducer.ts` | behavior adaptation | immutable streamed text/thinking/tool accumulation and snapshot replacement |
| `lib/message-display.ts` | `src/components/AgentChatPanel.tsx` | behavior reference | distinct assistant, thinking, Tool result and failure presentation |
| `lib/agent-event-connection.ts` | `src/hooks/useAgentConversation.ts` | rewritten | subscription before prompt and old-session isolation |
| `hooks/useAgentSession.ts` | `src/hooks/useAgentConversation.ts`, `src/events/terminal-state.ts` | rewritten | monotonic run, prompt admission, non-terminal agent pass, final settlement |
| `components/ChatWindow.tsx` | `src/components/AgentChatPanel.tsx` | visual adaptation | compact message layout and live status |
| `components/ChatInput.tsx` | `src/components/AgentChatPanel.tsx` | slim rewrite | IME-safe send, stop and queued follow-up |
| `components/MessageView.tsx` | `src/components/AgentChatPanel.tsx` | slim rewrite | typed messages, folded thinking and generic Tool cards |
| `components/MarkdownBody.tsx`, `lib/markdown.ts` | `src/rendering/SafeMarkdown.tsx`, `src/rendering/safe-render-policy.ts` | substantially modified | GFM/math rendering, sanitization and mediated navigation |
| `hooks/useI18n.tsx`, `hooks/useTheme.ts` | `src/i18n/I18nProvider.tsx`, `src/theme/ThemeProvider.tsx` | slim rewrite | mandatory provider wrappers and theme tokens |
| `components/ModelsConfig.tsx` | `src/contracts/agent-transport.ts` | behavior reference | isolated Provider status, credential change and test operations |

Deliberately absent are the upstream application server, project workspace shell, local project navigation, command execution, repository operations, extension surfaces, package installers, system-prompt editor, PWA/LAN surfaces, and provider discovery/catalog UI.

Every runtime operation is expressed by `AgentTransport` or `HostCapabilities`. UI components do not own an alternate network channel or a project authority.

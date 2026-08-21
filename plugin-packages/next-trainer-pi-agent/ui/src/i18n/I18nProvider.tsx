import { createContext, useContext, useMemo, type ReactNode } from "react";

export type UiLocale = "zh-CN" | "en";
export type MessageKey = keyof typeof messages.en;

const messages = {
  en: {
    assistant: "Training assistant",
    inputPlaceholder: "Ask about training, datasets, or results",
    send: "Send",
    stop: "Stop",
    reconnecting: "Reconnecting…",
    thinking: "Thinking",
    toolRunning: "Running {name}",
    providerSettings: "Provider settings",
    history: "History",
    empty: "Start a conversation about your training task.",
    error: "The request did not complete.",
    queued: "Queued",
    providerId: "Provider ID",
    endpoint: "Chat completions endpoint",
    modelId: "Model ID",
    apiKey: "API key",
    save: "Save",
    remove: "Remove",
    test: "Test",
    configured: "Configured",
    notConfigured: "Not configured",
  },
  "zh-CN": {
    assistant: "训练助手",
    inputPlaceholder: "询问训练参数、数据集或训练结果",
    send: "发送",
    stop: "停止",
    reconnecting: "正在重连…",
    thinking: "思考过程",
    toolRunning: "正在执行 {name}",
    providerSettings: "Provider 设置",
    history: "历史会话",
    empty: "从当前训练任务开始对话。",
    error: "请求未能完成。",
    queued: "已加入队列",
    providerId: "Provider ID",
    endpoint: "Chat Completions 地址",
    modelId: "模型 ID",
    apiKey: "API Key",
    save: "保存",
    remove: "移除",
    test: "测试",
    configured: "已配置",
    notConfigured: "未配置",
  },
} as const;

interface I18nContextValue {
  locale: UiLocale;
  t(key: MessageKey, params?: Record<string, string | number>): string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ locale, children }: { locale: UiLocale; children: ReactNode }) {
  const value = useMemo<I18nContextValue>(() => ({
    locale,
    t(key: MessageKey, params: Record<string, string | number> = {}) {
      let text: string = messages[locale][key] ?? messages.en[key];
      for (const [name, replacement] of Object.entries(params)) {
        text = text.replaceAll(`{${name}}`, String(replacement));
      }
      return text;
    },
  }), [locale]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const context = useContext(I18nContext);
  if (!context) throw new Error("useI18n must be used inside I18nProvider");
  return context;
}

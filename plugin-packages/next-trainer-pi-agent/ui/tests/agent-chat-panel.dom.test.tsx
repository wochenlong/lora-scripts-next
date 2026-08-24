import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { AgentChatPanel } from "../src/components/AgentChatPanel.tsx";
import { MemoryHostCapabilities } from "../src/testing/memory-host-capabilities.ts";
import { MemoryTransport } from "../src/testing/memory-transport.ts";
import { SlimUiTestWrapper } from "../src/testing/SlimUiTestWrapper.tsx";

function renderPanel(
  transport = new MemoryTransport(),
  host = new MemoryHostCapabilities(),
  initialSessionId: string | null = null,
) {
  const result = render(
    <SlimUiTestWrapper locale="zh-CN" scheme="dark">
      <AgentChatPanel
        transport={transport}
        host={host}
        initialSessionId={initialSessionId}
        modelLabel="remote-model"
      />
    </SlimUiTestWrapper>,
  );
  return { ...result, transport, host };
}

describe("AgentChatPanel", () => {
  test("fills the host-controlled floating panel instead of freezing its own 520×680 size", () => {
    renderPanel();
    const panel = screen.getByRole("region", { name: "训练助手" });
    expect(panel.classList.contains("nta-chat-panel")).toBe(true);
    expect(panel.style.width).toBe("100%");
    expect(panel.style.height).toBe("100%");
    expect(panel.closest("[data-color-scheme='dark']")).not.toBeNull();
    expect(screen.getByText("remote-model")).not.toBeNull();
  });

  test("opens the real host Provider settings route", async () => {
    const { host } = renderPanel();
    await userEvent.click(screen.getByRole("button", { name: "Provider 设置" }));
    await waitFor(() => expect(host.pluginRoutes).toEqual([
      "/settings/plugins/next-trainer-pi-agent",
    ]));
  });

  test("lists, resumes, renames, creates, and deletes sessions in the in-panel history drawer", async () => {
    const transport = new MemoryTransport();
    const first = await transport.sessions.create({ name: "参数讨论" });
    const second = await transport.sessions.create({ name: "数据集审计" });
    transport.operations.length = 0;
    renderPanel(transport, new MemoryHostCapabilities(), first.id);

    await userEvent.click(screen.getByRole("button", { name: "历史会话" }));
    await waitFor(() => expect(screen.getByText("数据集审计")).not.toBeNull());
    expect(transport.operations).toContain("sessions.list");

    await userEvent.click(screen.getByRole("button", { name: "继续会话：数据集审计" }));
    await waitFor(() => expect(transport.operations).toContain("sessions.getHistory"));

    await userEvent.click(screen.getByRole("button", { name: "历史会话" }));
    await waitFor(() => expect(screen.getByText("数据集审计")).not.toBeNull());
    await userEvent.click(screen.getByRole("button", { name: "重命名会话：数据集审计" }));
    const renameInput = screen.getByRole("textbox", { name: "会话名称" });
    await userEvent.clear(renameInput);
    await userEvent.type(renameInput, "审计结果");
    await userEvent.click(screen.getByRole("button", { name: "保存会话名称" }));
    await waitFor(() => expect(screen.getByText("审计结果")).not.toBeNull());
    expect(transport.operations).toContain("sessions.rename");

    await userEvent.click(screen.getByRole("button", { name: "新建会话" }));
    await waitFor(() => expect(transport.operations.filter((value) => value === "sessions.create").length).toBe(1));

    await userEvent.click(screen.getByRole("button", { name: "历史会话" }));
    await waitFor(() => expect(screen.getByText("审计结果")).not.toBeNull());
    await userEvent.click(screen.getByRole("button", { name: "删除会话：审计结果" }));
    await userEvent.click(screen.getByRole("button", { name: "确认删除会话：审计结果" }));
    await waitFor(() => expect(transport.operations).toContain("sessions.delete"));
    expect(screen.queryByText("审计结果")).toBeNull();
    expect(second.id).not.toBe(first.id);
  });

  test("IME Enter and Shift+Enter do not submit", async () => {
    const { transport } = renderPanel();
    const composer = screen.getByPlaceholderText("询问训练参数、数据集或训练结果") as HTMLTextAreaElement;
    const user = userEvent.setup();
    await user.type(composer, "正在输入");

    fireEvent.keyDown(composer, { key: "Enter", code: "Enter", isComposing: true });
    fireEvent.keyDown(composer, { key: "Enter", code: "Enter", shiftKey: true });

    expect(composer.value).toBe("正在输入");
    expect(transport.operations.includes("sessions.prompt")).toBe(false);
  });

  test("ordinary Enter subscribes before prompt admission and clears an accepted draft", async () => {
    const { transport } = renderPanel();
    const composer = screen.getByPlaceholderText("询问训练参数、数据集或训练结果") as HTMLTextAreaElement;
    const user = userEvent.setup();
    await user.type(composer, "请分析训练参数{Enter}");

    await waitFor(() => expect(transport.operations).toContain("sessions.prompt"));
    const subscribeIndex = transport.operations.indexOf("sessions.subscribe");
    const promptIndex = transport.operations.indexOf("sessions.prompt");
    expect(subscribeIndex).toBeGreaterThanOrEqual(0);
    expect(subscribeIndex).toBeLessThan(promptIndex);
    await waitFor(() => expect(composer.value).toBe(""));
    expect(screen.getByText("请分析训练参数")).not.toBeNull();
  });

  test("new sessions cannot inherit messages from the previously selected session", async () => {
    const transport = new MemoryTransport();
    const oldSession = await transport.sessions.create({ name: "旧会话" });
    await transport.sessions.prompt(oldSession.id, {
      text: "只属于旧会话的内容",
      clientSubmissionId: "old-message",
    });
    transport.emit({
      type: "prompt_done",
      eventId: "old-done",
      sessionId: oldSession.id,
      runId: 1,
    });
    renderPanel(transport, new MemoryHostCapabilities(), oldSession.id);
    await waitFor(() => expect(screen.getByText("只属于旧会话的内容")).not.toBeNull());

    await userEvent.click(screen.getByRole("button", { name: "历史会话" }));
    await userEvent.click(screen.getByRole("button", { name: "新建会话" }));
    await waitFor(() => expect(screen.queryByText("只属于旧会话的内容")).toBeNull());
  });
});

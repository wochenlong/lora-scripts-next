import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { AgentChatPanel } from "../src/components/AgentChatPanel.tsx";
import { MemoryHostCapabilities } from "../src/testing/memory-host-capabilities.ts";
import { MemoryTransport } from "../src/testing/memory-transport.ts";
import { SlimUiTestWrapper } from "../src/testing/SlimUiTestWrapper.tsx";

function renderPanel(transport = new MemoryTransport(), host = new MemoryHostCapabilities()) {
  const result = render(
    <SlimUiTestWrapper locale="zh-CN" scheme="dark">
      <AgentChatPanel transport={transport} host={host} modelLabel="remote-model" />
    </SlimUiTestWrapper>,
  );
  return { ...result, transport, host };
}

describe("AgentChatPanel", () => {
  test("renders inside the mandatory locale/theme wrapper with the 520×680 floating-panel contract", () => {
    renderPanel();
    const panel = screen.getByRole("region", { name: "训练助手" });
    expect(panel.classList.contains("nta-chat-panel")).toBe(true);
    expect(panel.style.width).toBe("520px");
    expect(panel.style.maxWidth).toBe("100%");
    expect(panel.style.height).toBe("680px");
    expect(panel.style.maxHeight).toBe("100%");
    expect(panel.closest("[data-color-scheme='dark']")).not.toBeNull();
    expect(screen.getByText("remote-model")).not.toBeNull();
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
});






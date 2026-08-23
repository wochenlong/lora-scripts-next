import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { ProviderSettingsPanel } from "../src/components/ProviderSettingsPanel.tsx";
import { MemoryTransport } from "../src/testing/memory-transport.ts";
import { SlimUiTestWrapper } from "../src/testing/SlimUiTestWrapper.tsx";

describe("ProviderSettingsPanel", () => {
  test("submits a raw key once, clears the field, and never writes browser storage", async () => {
    const transport = new MemoryTransport();
    transport.seedProvider({
      id: "remote",
      label: "Remote",
      endpoint: "https://example.invalid/v1/chat/completions",
      modelId: "model",
      configured: false,
    });
    const storageWrite = vi.spyOn(Storage.prototype, "setItem");
    const user = userEvent.setup();
    render(
      <SlimUiTestWrapper>
        <ProviderSettingsPanel transport={transport} />
      </SlimUiTestWrapper>,
    );

    const keyInput = await screen.findByLabelText("API Key") as HTMLInputElement;
    const rawKey = "raw-key-value-9876";
    await user.type(keyInput, rawKey);
    await user.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(screen.getByText(/已配置/)).not.toBeNull());
    expect(keyInput.value).toBe("");
    expect(document.body.textContent?.includes(rawKey)).toBe(false);
    expect(globalThis.localStorage.getItem("provider-key")).toBeNull();
    expect(globalThis.sessionStorage.getItem("provider-key")).toBeNull();
    expect(storageWrite).not.toHaveBeenCalled();

    const status = await transport.providers.status("remote");
    expect("key" in status).toBe(false);
    expect(JSON.stringify(status).includes(rawKey)).toBe(false);
  });
});






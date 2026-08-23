import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { SafeMarkdown } from "../src/rendering/SafeMarkdown.tsx";
import { MemoryHostCapabilities } from "../src/testing/memory-host-capabilities.ts";
import { SlimUiTestWrapper } from "../src/testing/SlimUiTestWrapper.tsx";

function renderMarkdown(markdown: string, host = new MemoryHostCapabilities()) {
  const result = render(
    <SlimUiTestWrapper>
      <SafeMarkdown host={host}>{markdown}</SafeMarkdown>
    </SlimUiTestWrapper>,
  );
  return { ...result, host };
}

describe("SafeMarkdown", () => {
  test("removes executable and navigational HTML elements", () => {
    const { container } = renderMarkdown(`
<script>globalThis.compromised = true</script>
<form action="https://example.invalid"><input name="secret"></form>
<iframe src="https://example.invalid"></iframe>
<object data="https://example.invalid"></object>
<style>body { display: none }</style>
<p>safe text</p>
    `);
    for (const selector of ["script", "form", "input", "iframe", "object", "style"]) {
      expect(container.querySelector(selector)).toBeNull();
    }
    expect(screen.getByText("safe text")).not.toBeNull();
  });

  test("delegates an external link to HostCapabilities without creating a navigable anchor", async () => {
    const { container, host } = renderMarkdown("[官方说明](https://example.com/docs)");
    const user = userEvent.setup();
    expect(container.querySelector("a")).toBeNull();
    await user.click(screen.getByRole("button", { name: "官方说明" }));
    await waitFor(() => expect(host.openedExternal).toEqual(["https://example.com/docs"]));
  });

  test("blocks remote and vector image sources while retaining safe inline raster data", () => {
    const { container } = renderMarkdown(`
![remote](https://example.com/a.png)
![vector](data:image/svg+xml;base64,PHN2Zz4=)
![raster](data:image/png;base64,iVBORw0KGgo=)
    `);
    expect(container.querySelectorAll("img")).toHaveLength(1);
    expect(container.querySelector("img")?.getAttribute("alt")).toBe("raster");
    expect(screen.getByText("[remote]")).not.toBeNull();
    expect(screen.getByText("[vector]")).not.toBeNull();
  });
});






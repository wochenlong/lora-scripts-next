// @vitest-environment jsdom
import { mount } from "@vue/test-utils"
import { nextTick } from "vue"
import { describe, expect, it } from "vitest"
import type { PluginConfirmationProjection } from "../../api/plugins"
import { i18n } from "../../i18n"
import HostConfirmationLayer from "./HostConfirmationLayer.vue"

function confirmation(overrides: Partial<PluginConfirmationProjection> = {}): PluginConfirmationProjection {
  return {
    ticketId: "ticket-1",
    pluginId: "sample-plugin",
    toolCallId: "tool-1",
    state: "presented",
    permission: "caption-commit",
    action: "caption.commit",
    title: "Apply caption changes",
    summary: "Update 4 caption files after validating their revisions.",
    artifactIds: ["changeset-1"],
    details: { files: 4 },
    createdAt: "2098-01-01T00:00:00Z",
    expiresAt: "2099-01-01T00:00:00Z",
    resolvedAt: null,
    ...overrides,
  }
}

describe("HostConfirmationLayer", () => {
  it("renders a host-owned dialog outside any iframe and rejects by default focus", async () => {
    const wrapper = mount(HostConfirmationLayer, {
      attachTo: document.body,
      props: { confirmation: confirmation(), pluginName: "Sample Assistant" },
      global: { plugins: [i18n] },
    })
    await nextTick()

    expect(wrapper.attributes("role")).toBe("dialog")
    expect(wrapper.text()).toContain("Next Trainer 宿主确认")
    expect(wrapper.text()).toContain("Apply caption changes")
    expect(wrapper.text()).toContain("changeset-1")
    expect(wrapper.find("iframe").exists()).toBe(false)
    expect(document.activeElement).toBe(wrapper.get<HTMLButtonElement>("button.secondary-action").element)

    await wrapper.get("button.secondary-action").trigger("click")
    expect(wrapper.emitted("resolve")?.[0]).toEqual(["rejected"])
    wrapper.unmount()
  })

  it("approves explicitly and traps keyboard focus inside the host layer", async () => {
    const wrapper = mount(HostConfirmationLayer, {
      attachTo: document.body,
      props: { confirmation: confirmation(), pluginName: "Sample Assistant" },
      global: { plugins: [i18n] },
    })
    await nextTick()
    const reject = wrapper.get<HTMLButtonElement>("button.secondary-action")
    const approve = wrapper.get<HTMLButtonElement>("button.primary-action")

    reject.element.focus()
    await reject.trigger("keydown", { key: "Tab" })
    expect(document.activeElement).toBe(approve.element)
    await approve.trigger("click")
    expect(wrapper.emitted("resolve")?.[0]).toEqual(["approved"])
    wrapper.unmount()
  })

  it("does not approve an expired ticket", async () => {
    const wrapper = mount(HostConfirmationLayer, {
      props: {
        confirmation: confirmation({ expiresAt: "2020-01-01T00:00:00Z" }),
        pluginName: "Sample Assistant",
      },
      global: { plugins: [i18n] },
    })
    const approve = wrapper.get("button.primary-action")
    expect(approve.attributes("disabled")).toBeDefined()
    await approve.trigger("click")
    expect(wrapper.emitted("resolve")).toBeUndefined()
    wrapper.unmount()
  })
})

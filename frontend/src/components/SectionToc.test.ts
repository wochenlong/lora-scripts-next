// @vitest-environment jsdom
import { mount } from "@vue/test-utils"
import { describe, expect, it, vi } from "vitest"
import SectionToc from "./SectionToc.vue"
import { i18n } from "../i18n"

const sections = [
  { id: "basic", title: "基础参数" },
  { id: "network", title: "网络设置" },
]

describe("SectionToc", () => {
  it("starts collapsed and expands on seam click", async () => {
    const wrapper = mount(SectionToc, { props: { sections }, global: { plugins: [i18n] } })
    expect(wrapper.classes()).not.toContain("open")
    await wrapper.get(".toc-seam").trigger("click")
    expect(wrapper.classes()).toContain("open")
    expect(wrapper.text()).toContain("基础参数")
    expect(wrapper.text()).toContain("网络设置")
    await wrapper.get(".toc-panel header button").trigger("click")
    expect(wrapper.classes()).not.toContain("open")
  })

  it("navigates to the section anchor and retracts after selection", async () => {
    const target = document.createElement("div")
    target.id = "sec-network"
    const scrollIntoView = vi.fn()
    target.scrollIntoView = scrollIntoView
    document.body.appendChild(target)
    const wrapper = mount(SectionToc, { props: { sections }, global: { plugins: [i18n] } })
    await wrapper.get(".toc-seam").trigger("click")
    const items = wrapper.findAll(".toc-item")
    await items[1].trigger("click")
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" })
    expect(wrapper.classes()).not.toContain("open")
    target.remove()
  })
})

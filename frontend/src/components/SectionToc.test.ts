// @vitest-environment jsdom
import { mount } from "@vue/test-utils"
import { describe, expect, it, vi } from "vitest"
import SectionToc from "./SectionToc.vue"
import { i18n } from "../i18n"

const sections = [
  { id: "basic", title: "基础参数" },
  { id: "network", title: "网络设置" },
]

function mountToc(props: { sections?: { id: string; title: string }[] } = {}) {
  return mount(SectionToc, { props: { sections: sections, ...props }, global: { plugins: [i18n] } })
}

describe("SectionToc", () => {
  it("opens on hover and stays open until the pointer leaves", async () => {
    const wrapper = mountToc()
    expect(wrapper.classes()).not.toContain("open")
    await wrapper.trigger("mouseenter")
    expect(wrapper.classes()).toContain("open")
    expect(wrapper.text()).toContain("基础参数")
    expect(wrapper.text()).toContain("网络设置")
    await wrapper.trigger("mouseleave")
    expect(wrapper.classes()).not.toContain("open")
  })

  it("pins open on seam click and ignores mouseleave until toggled again", async () => {
    const wrapper = mountToc()
    await wrapper.get(".toc-seam").trigger("click")
    expect(wrapper.classes()).toContain("open")
    await wrapper.trigger("mouseenter")
    await wrapper.trigger("mouseleave")
    expect(wrapper.classes()).toContain("open")
    await wrapper.get(".toc-panel header button").trigger("click")
    expect(wrapper.classes()).not.toContain("open")
  })

  it("navigates on item click without closing a pinned panel", async () => {
    const target = document.createElement("div")
    target.id = "sec-network"
    const scrollIntoView = vi.fn()
    target.scrollIntoView = scrollIntoView
    document.body.appendChild(target)
    const wrapper = mountToc()
    await wrapper.get(".toc-seam").trigger("click")
    const items = wrapper.findAll(".toc-item")
    await items[1].trigger("click")
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" })
    expect(wrapper.classes()).toContain("open")
    target.remove()
  })

  it("stays closed and disabled when there are no sections yet", async () => {
    const wrapper = mountToc({ sections: [] })
    expect(wrapper.classes()).toContain("empty")
    expect(wrapper.get(".toc-seam").attributes("disabled")).toBeDefined()
    await wrapper.trigger("mouseenter")
    expect(wrapper.classes()).not.toContain("open")
  })
})

// @vitest-environment jsdom
import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"
import { i18n } from "../i18n"
import type { TaggerModel } from "../api/tagger"
import TaggerModelSelector from "./TaggerModelSelector.vue"

const models: TaggerModel[] = [
  { id: "wd-vit-v3", name: "WD", model: "wd-vit-v3", family: "WD", author: "SmilingWolf", runtime: "local", output: "tag", ready: true, downloaded: true, profile_id: null, capabilities: ["tag"], languages: ["native"], parameters: [] },
  { id: "llm:qwen", name: "Qwen", model: "Qwen3-VL-2B", family: "Qwen-VL", author: "Qwen", runtime: "local", output: "natural", ready: false, downloaded: false, profile_id: "qwen", capabilities: ["vision", "caption"], languages: ["zh-CN"], parameters: [] },
]

describe("model family selector", () => {
  it("expands only the current family and shows the exact selected model", () => {
    const page = mount(TaggerModelSelector, { props: { models, selected: "wd-vit-v3", disabled: false }, global: { plugins: [i18n] } })
    expect(page.get("summary").text()).toContain("wd-vit-v3")
    expect(page.get("summary").text()).toContain("已下载")
    const families = page.findAll(".tagger-model-family")
    expect(families[0].attributes("open")).toBeDefined()
    expect(families[1].attributes("open")).toBeUndefined()
    page.unmount()
  })

  it("searches original names and expands matches without changing selection", async () => {
    const page = mount(TaggerModelSelector, { props: { models, selected: "wd-vit-v3", disabled: false }, global: { plugins: [i18n] } })
    await page.get('input[type="search"]').setValue("Qwen3-VL")
    expect(page.findAll(".tagger-model-family")).toHaveLength(1)
    expect(page.get(".tagger-model-family").attributes("open")).toBeDefined()
    await page.get('[data-model-id="llm:qwen"]').trigger("click")
    expect(page.emitted("select")).toEqual([["llm:qwen"]])
    expect((page.get('input[type="search"]').element as HTMLInputElement).value).toBe("")
    page.unmount()
  })
})

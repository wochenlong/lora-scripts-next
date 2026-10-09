// @vitest-environment jsdom
import { beforeEach, expect, it, vi } from "vitest"
import { DOWNLOAD_SOURCES_KEY, chinaDownloadSources } from "../engines/downloadSources"

const { apiRequest } = vi.hoisted(() => ({ apiRequest: vi.fn() }))
vi.mock("./client", () => ({
  apiData: vi.fn(),
  apiRequest,
}))

import { taggerApi, type TaggerRequest } from "./tagger"

beforeEach(() => {
  localStorage.clear()
  apiRequest.mockReset()
})

it("uses the Hugging Face endpoint configured in settings for tagger requests", async () => {
  localStorage.setItem(DOWNLOAD_SOURCES_KEY, JSON.stringify(chinaDownloadSources()))
  const request: TaggerRequest = {
    path: "/images",
    interrogator_model: "wd14-convnextv2-v2",
    threshold: 0.35,
    character_threshold: 0.6,
    add_rating_tag: false,
    add_model_tag: false,
    additional_tags: "",
    exclude_tags: "",
    escape_tag: true,
    batch_input_recursive: false,
    batch_output_action_on_conflict: "ignore",
    replace_underscore: true,
    replace_underscore_excludes: "",
  }

  await taggerApi.start(request)

  const body = JSON.parse(apiRequest.mock.calls[0][1].body)
  expect(body.download_endpoint).toBe("https://hf-mirror.com")
})

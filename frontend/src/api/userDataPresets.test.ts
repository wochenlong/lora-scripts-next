import { afterEach, expect, it, vi } from "vitest"
import { taskArchivesApi } from "./taskArchives"
import { userPresetsApi } from "./userPresets"

afterEach(() => vi.restoreAllMocks())

it("uses encoded, typed user preset CRUD endpoints", async () => {
  const fetcher = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input)
    if (init?.method === "POST") return new Response(JSON.stringify({ status: "success", data: { id: "p1", name: "A", config: {} } }))
    if (init?.method === "PATCH") return new Response(JSON.stringify({ status: "success", data: { id: "p/1", name: "B", config: {} } }))
    if (init?.method === "DELETE") return new Response(JSON.stringify({ status: "success", data: { removed: true } }))
    expect(url).toBe("/api/user-data/presets?train_type=sd%2Fxl")
    return new Response(JSON.stringify({ status: "success", data: { presets: [{ id: "p1", name: "A", config: {} }] } }))
  })
  expect(await userPresetsApi.list("sd/xl")).toHaveLength(1)
  expect(await userPresetsApi.create({ name: "A", config: {}, train_type: "sd/xl" })).toMatchObject({ id: "p1" })
  await userPresetsApi.update("p/1", { name: "B" })
  await userPresetsApi.remove("p/1")
  expect(fetcher).toHaveBeenCalledTimes(4)
})

it("lists and loads task archives through the shared user-data API", async () => {
  const archive = { id: "a1", name: "run", train_type: "anima-lora-fast", config: { max_train_steps: 100 } }
  const fetcher = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const data = String(input).includes("/task-archives/") ? archive : { archives: [archive] }
    return new Response(JSON.stringify({ status: "success", data }))
  })
  expect(await taskArchivesApi.list("anima-lora-fast")).toEqual([archive])
  expect(await taskArchivesApi.get("a/1")).toEqual(archive)
  expect(fetcher).toHaveBeenLastCalledWith("/api/user-data/task-archives/a%2F1", expect.anything())
  expect(fetcher).toHaveBeenCalledTimes(2)
})

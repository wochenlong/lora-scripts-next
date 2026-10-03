import { describe, expect, it } from "vitest"
import { collectDatasetCheckTargets } from "./datasetCheck"

describe("collectDatasetCheckTargets", () => {
  it("collects non-empty scalar dataset dirs", () => {
    expect(collectDatasetCheckTargets({ train_data_dir: "./datasets/a", reg_data_dir: "  " })).toEqual(["./datasets/a"])
  })

  it("collects array dirs and dedupes", () => {
    const targets = collectDatasetCheckTargets({
      train_data_dir: "/data/out",
      output_data_dir: "/data/out",
      input_data_dirs: ["/data/in-a", " /data/in-b ", 42, ""],
    })
    expect(targets).toEqual(["/data/out", "/data/in-a", "/data/in-b"])
  })

  it("collects metadata-mode dataset_base_path", () => {
    expect(collectDatasetCheckTargets({ dataset_base_path: "./datasets/qwen-meta" })).toEqual(["./datasets/qwen-meta"])
  })

  it("returns empty when nothing is set", () => {
    expect(collectDatasetCheckTargets({})).toEqual([])
  })
})

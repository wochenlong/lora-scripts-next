import type { FormModel } from "../schema/adapter"

const SCALAR_DIR_KEYS = ["train_data_dir", "reg_data_dir", "output_data_dir", "dataset_base_path"] as const
const ARRAY_DIR_KEYS = ["input_data_dirs"] as const

/** Collect non-empty dataset directory values from a training form model. */
export function collectDatasetCheckTargets(model: FormModel): string[] {
  const targets: string[] = []
  for (const key of SCALAR_DIR_KEYS) {
    const value = model[key]
    if (typeof value === "string" && value.trim()) targets.push(value.trim())
  }
  for (const key of ARRAY_DIR_KEYS) {
    const value = model[key]
    if (!Array.isArray(value)) continue
    for (const item of value) {
      if (typeof item === "string" && item.trim()) targets.push(item.trim())
    }
  }
  return [...new Set(targets)]
}

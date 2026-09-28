import type { FormModel } from "../schema/adapter"

export const QWEN_VALIDATION_FIELDS = ["training_task", "train_batch_size", "preview_samples"] as const

/** Shared field errors for schema validation and the live submission diagnostics. */
export function validateQwenConfig(config: FormModel): Record<string, string> {
  const errors: Record<string, string> = {}
  const task = config.training_task === undefined ? "text-to-image" : config.training_task
  if (task !== "text-to-image" && task !== "image-edit") {
    errors.training_task = "训练模式无效，请重新选择文生图 T2I 或 Edit 图像编辑。"
    return errors
  }
  if (task !== "image-edit") return errors
  if (Number(config.train_batch_size ?? 1) !== 1) {
    errors.train_batch_size = "Edit 的 train_batch_size 必须为 1；可通过 gradient_accumulation_steps 增加有效批大小。"
  }
  if (!config.sample_enabled) return errors
  const samples = config.preview_samples
  if (!Array.isArray(samples) || !samples.length) {
    errors.preview_samples = "Edit 预览至少需要一个样例及参考图。"
    return errors
  }
  const problems: string[] = []
  samples.forEach((value, index) => {
    try {
      const sample: unknown = typeof value === "string" ? JSON.parse(value) : null
      if (!sample || typeof sample !== "object" || !("controlImages" in sample)
        || !Array.isArray(sample.controlImages) || !sample.controlImages.length
        || sample.controlImages.some(path => typeof path !== "string" || !path.trim())) {
        problems.push(`预览样例 ${index + 1}：至少填写一张参考图的非空路径。`)
      }
    } catch { problems.push(`预览样例 ${index + 1}：配置格式无效。`) }
  })
  if (problems.length) errors.preview_samples = problems.join(" ")
  return errors
}

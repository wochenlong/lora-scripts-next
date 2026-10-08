import type { CaptionPromptPreset } from "../api/llm"

export const englishCaptionPrompt = 'Describe the main visible content of the image in {{language}} (en means English). Return only a JSON object with exactly caption and language; language must be "{{language}}". Do not output Markdown.'
export const captionBuiltins: CaptionPromptPreset[] = [
  { id: "builtin-caption-en", kind: "caption_prompt", name: "Visible facts / 客观描述（英文）", template: englishCaptionPrompt, system_prompt: "Describe only visible subjects, actions, environment and composition. Do not infer identities or invisible facts. Follow the requested output language strictly.", output_format: "plain_text", language: "en", max_length: 2000, model_capabilities: ["vision", "caption"], revision: "builtin-en-v2" },
  { id: "builtin-caption-zh", kind: "caption_prompt", name: "客观描述（中文） / Visible facts", template: '请用{{language}}描述图片中的主要可见内容，只返回 JSON 对象，字段必须为 caption 和 language；language 必须是 "{{language}}"，不要输出 Markdown。', system_prompt: "只描述可见主体、动作、环境和构图，不臆测身份或不可见事实，严格遵守请求的输出语言。", output_format: "plain_text", language: "zh-CN", max_length: 2000, model_capabilities: ["vision", "caption"], revision: "builtin-zh-v2" },
]

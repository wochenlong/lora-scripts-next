/**
 * CLIP 词元数估算：按空格/下划线分词，每个词计 1 个词元；
 * 超长词（>15 字符）超出部分每 6 字符追加 1 个词元。
 * 估算值，非精确 tokenizer 计数，仅用于 tag 列表排序。
 */
export function estimateTokenLength(tag: string): number {
  const words = tag.split(/[\s_]+/).filter(Boolean)
  if (!words.length) return 0
  return words.reduce((total, word) => total + 1 + (word.length > 15 ? Math.ceil((word.length - 15) / 6) : 0), 0)
}

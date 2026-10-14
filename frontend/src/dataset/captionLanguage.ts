export function isChineseCaption(text: string): boolean {
  if (!/[\u3400-\u9fff]/.test(text) || /[\u3040-\u30ff\u31f0-\u31ff\uff66-\uff9f]/.test(text)) return false
  // Quoted signs are image content, rather than evidence of the caption's
  // language. Brand names may remain Latin inside a Chinese description.
  let body = text.replace(/"[^"]*"|“[^”]*”|「[^」]*」|『[^』]*』/g, " ")
    .replace(/(?<![A-Za-z0-9])'[^'\r\n]*'(?![A-Za-z0-9])/g, " ")
  if (!/[A-Za-z\u3400-\u9fff]/.test(body)) body = text
  const functionWords = new Set(["the", "a", "an", "is", "are", "was", "were", "with", "of", "on", "in", "at", "to", "for", "and", "or", "next", "beside", "behind", "under", "above", "shows", "says", "reads"])
  for (const sentence of body.split(/[.!?。！？\r\n]+/)) {
    if (/^\s*(?:a|an|the|this|that|these|those)[ \t]+[A-Za-z]+/i.test(sentence)) return false
    for (const run of sentence.match(/[A-Za-z]+(?:[ \t,]+[A-Za-z]+)*/g) ?? []) {
      const words = run.toLowerCase().split(/[ \t,]+/)
      if (words.filter(word => functionWords.has(word)).length >= 2) return false
    }
  }
  const han = body.match(/[\u3400-\u9fff]/g)?.length || 0
  return han > 0 && han >= (body.match(/[A-Za-z]+/g)?.length || 0)
}

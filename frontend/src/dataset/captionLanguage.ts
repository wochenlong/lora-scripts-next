export function isChineseCaption(text: string): boolean {
  const han = text.match(/[\u3400-\u9fff]/g)?.length || 0
  return han > 0 && !/[\u3040-\u30ff]/.test(text) && han >= (text.match(/[A-Za-z]+/g)?.length || 0)
}

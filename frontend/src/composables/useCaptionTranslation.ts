import { ref } from "vue"
import { llmApi } from "../api/llm"
import { isChineseCaption } from "../dataset/captionLanguage"

export function useCaptionTranslation() {
  const text = ref("")
  const loading = ref(false)
  const error = ref("")
  const alreadyChinese = ref(false)
  let generation = 0
  let controller: AbortController | undefined
  function cancel() {
    generation += 1
    controller?.abort()
    controller = undefined
    loading.value = false
    text.value = ""
    error.value = ""
    alreadyChinese.value = false
  }
  async function translate(source: string, allowLocalFallback = false) {
    cancel()
    source = source.trim()
    if (!source) return
    if (isChineseCaption(source)) {
      text.value = source
      alreadyChinese.value = true
      return
    }
    const requestGeneration = generation
    controller = new AbortController()
    loading.value = true
    try {
      const result = await llmApi.translateCaption(source, allowLocalFallback, controller.signal)
      if (generation === requestGeneration) {
        text.value = result.translation
        alreadyChinese.value = result.skipped
      }
    } catch (caught) {
      if (generation === requestGeneration) error.value = caught instanceof Error ? caught.message : String(caught)
    } finally {
      if (generation === requestGeneration) loading.value = false
    }
  }
  return { text, loading, error, alreadyChinese, translate, cancel }
}

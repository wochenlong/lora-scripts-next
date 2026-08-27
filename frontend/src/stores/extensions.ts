import { computed, ref } from "vue"
import { defineStore } from "pinia"
import {
  isSafePluginServerUiUrl,
  isSafePluginUiUrl,
  isValidPluginId,
  pluginsApi,
  type PluginHostExtension,
} from "../api/plugins"

const visibleStates = new Set(["starting", "ready", "runtime_error", "provider_error"])

function validExtension(extension: PluginHostExtension) {
  return isValidPluginId(extension.pluginId) && Boolean(extension.displayName.trim())
}

function hasSafeFloatingEntry(extension: PluginHostExtension) {
  const entry = extension.ui.floatingPanel
  if (!entry) return false
  if (entry.mode === "server") return isSafePluginServerUiUrl(entry.entryUrl)
  return isSafePluginUiUrl(entry.entryUrl, extension.pluginId)
}

export const useExtensionsStore = defineStore("extensions", () => {
  const extensions = ref<PluginHostExtension[]>([])
  const loaded = ref(false)
  const loading = ref(false)
  const error = ref("")

  const floatingExtensions = computed(() =>
    extensions.value.filter(
      (extension) =>
        validExtension(extension) &&
        extension.enabled &&
        visibleStates.has(extension.state) &&
        hasSafeFloatingEntry(extension),
    ),
  )

  async function refresh() {
    if (loading.value) return
    loading.value = true
    error.value = ""
    try {
      await pluginsApi.ensureHostAuthority()
      const result = await pluginsApi.listExtensions()
      extensions.value = result.extensions.filter(validExtension)
    } catch (reason) {
      extensions.value = []
      void reason
      error.value = "Plugin host is unavailable."
    } finally {
      loaded.value = true
      loading.value = false
    }
  }

  async function ensureLoaded() {
    if (!loaded.value) await refresh()
  }

  function find(pluginId: string) {
    return extensions.value.find((extension) => extension.pluginId === pluginId)
  }

  return { extensions, floatingExtensions, loaded, loading, error, refresh, ensureLoaded, find }
})

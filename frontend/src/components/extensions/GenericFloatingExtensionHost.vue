<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { storeToRefs } from "pinia"
import { useRoute, useRouter } from "vue-router"
import { useI18n } from "vue-i18n"
import {
  isSafePluginServerUiUrl,
  isSafePluginUiUrl,
  pluginsApi,
  type PluginConfirmationDecision,
  type PluginConfirmationProjection,
  type PluginHostExtension,
} from "../../api/plugins"
import agentIcon from "../../assets/svg-256.png"
import { HostPluginBridge, type BridgeFrameTarget } from "../../extensions/pluginBridge"
import { createPluginFrameBridge, createPluginFrameInstanceId } from "../../extensions/pluginFrameBridge"
import { useExtensionsStore } from "../../stores/extensions"
import HostConfirmationLayer from "./HostConfirmationLayer.vue"

const PREFERENCE_PREFIX = "plugin-floating-panel:"
const DEFAULT_PANEL_WIDTH = 520
const DEFAULT_PANEL_HEIGHT = 680
const MIN_PANEL_WIDTH = 420
const MIN_PANEL_HEIGHT = 480
const MAX_PANEL_WIDTH = 760
const VIEWPORT_GUTTER = 32
const VIEWPORT_VERTICAL_RESERVE = 96
const route = useRoute()
const router = useRouter()
const { locale, t } = useI18n()
const extensionsStore = useExtensionsStore()
const { floatingExtensions } = storeToRefs(extensionsStore)
// Every enabled floating-panel extension gets its own launcher (Copilot C-4);
// this tracks which plugin the user selected. An unknown/removed id falls back
// to the first extension so the panel is never orphaned.
const selectedPluginId = ref<string>("")
const activeExtension = computed(
  () =>
    floatingExtensions.value.find((item) => item.pluginId === selectedPluginId.value) ??
    floatingExtensions.value[0] ??
    null,
)
const frame = ref<HTMLIFrameElement | null>(null)
const frameSrc = ref("about:blank")
const panelOpen = ref(false)
const panelWidth = ref(DEFAULT_PANEL_WIDTH)
const panelHeight = ref(DEFAULT_PANEL_HEIGHT)
const viewportWidth = ref(window.innerWidth)
const pendingConfirmations = ref<PluginConfirmationProjection[]>([])
const confirmation = computed(
  () => pendingConfirmations.value.find((value) => value.pluginId === activeExtension.value?.pluginId) ?? null,
)
const confirmationBusy = ref(false)
const confirmationError = ref("")
let bridge: HostPluginBridge | null = null
let resizeOrigin: { x: number; y: number; width: number; height: number } | null = null

const panelStyle = computed(() =>
  viewportWidth.value > 768 ? { width: `${panelWidth.value}px`, height: `${panelHeight.value}px` } : undefined,
)

function preferenceKey(pluginId: string) {
  return `${PREFERENCE_PREFIX}${pluginId}`
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(Math.max(value, minimum), maximum)
}

function clampPanelSize(width: number, height: number) {
  const maxWidth = Math.max(1, Math.min(MAX_PANEL_WIDTH, window.innerWidth - VIEWPORT_GUTTER))
  const maxHeight = Math.max(1, window.innerHeight - VIEWPORT_VERTICAL_RESERVE)
  return {
    width: clamp(width, Math.min(MIN_PANEL_WIDTH, maxWidth), maxWidth),
    height: clamp(height, Math.min(MIN_PANEL_HEIGHT, maxHeight), maxHeight),
  }
}

function readPanelPreference(pluginId: string) {
  try {
    const value = JSON.parse(localStorage.getItem(preferenceKey(pluginId)) || "{}") as {
      open?: unknown
      width?: unknown
      height?: unknown
    }
    const size = clampPanelSize(
      typeof value.width === "number" && Number.isFinite(value.width) ? value.width : DEFAULT_PANEL_WIDTH,
      typeof value.height === "number" && Number.isFinite(value.height) ? value.height : DEFAULT_PANEL_HEIGHT,
    )
    return { open: value.open === true, ...size }
  } catch {
    return { open: false, ...clampPanelSize(DEFAULT_PANEL_WIDTH, DEFAULT_PANEL_HEIGHT) }
  }
}

function saveOpenPreference() {
  const extension = activeExtension.value
  if (!extension) return
  localStorage.setItem(
    preferenceKey(extension.pluginId),
    JSON.stringify({ open: panelOpen.value, width: panelWidth.value, height: panelHeight.value }),
  )
}

function applyPanelSize(width: number, height: number) {
  const size = clampPanelSize(width, height)
  panelWidth.value = size.width
  panelHeight.value = size.height
}

function stopResize() {
  if (!resizeOrigin) return
  resizeOrigin = null
  window.removeEventListener("pointermove", onResizeMove)
  window.removeEventListener("pointerup", stopResize)
  saveOpenPreference()
}

function onResizeMove(event: PointerEvent) {
  if (!resizeOrigin) return
  applyPanelSize(
    resizeOrigin.width + resizeOrigin.x - event.clientX,
    resizeOrigin.height + resizeOrigin.y - event.clientY,
  )
}

function startResize(event: PointerEvent) {
  if (window.innerWidth <= 768) return
  event.preventDefault()
  resizeOrigin = {
    x: event.clientX,
    y: event.clientY,
    width: panelWidth.value,
    height: panelHeight.value,
  }
  window.addEventListener("pointermove", onResizeMove)
  window.addEventListener("pointerup", stopResize)
}

function resizeWithKeyboard(event: KeyboardEvent) {
  const step = event.shiftKey ? 32 : 16
  const deltas: Partial<Record<string, [number, number]>> = {
    ArrowLeft: [step, 0],
    ArrowRight: [-step, 0],
    ArrowUp: [0, step],
    ArrowDown: [0, -step],
  }
  const delta = deltas[event.key]
  if (!delta) return
  event.preventDefault()
  applyPanelSize(panelWidth.value + delta[0], panelHeight.value + delta[1])
  saveOpenPreference()
}

function onViewportResize() {
  viewportWidth.value = window.innerWidth
  applyPanelSize(panelWidth.value, panelHeight.value)
}

function disposeBridge() {
  bridge?.dispose()
  bridge = null
  frameSrc.value = "about:blank"
}

function upsertConfirmation(value: PluginConfirmationProjection) {
  pendingConfirmations.value = [value, ...pendingConfirmations.value.filter((item) => item.ticketId !== value.ticketId)]
  confirmationError.value = ""
}

async function refreshPendingConfirmations() {
  try {
    pendingConfirmations.value = await pluginsApi.listPendingConfirmations()
  } catch {
    pendingConfirmations.value = []
  }
}

function isServerEntry(extension: PluginHostExtension) {
  const entry = extension.ui.floatingPanel
  return entry?.mode === "server" && isSafePluginServerUiUrl(entry.entryUrl)
}

async function activateExtension(extension: PluginHostExtension | null) {
  disposeBridge()
  const server = extension ? isServerEntry(extension) : false
  const entryUrl = server
    ? extension!.ui.floatingPanel!.entryUrl
    : extension
      ? isSafePluginUiUrl(extension.ui.floatingPanel?.entryUrl, extension.pluginId)
        ? extension.ui.floatingPanel!.entryUrl
        : ""
      : ""
  if (!extension || !entryUrl) {
    panelOpen.value = false
    pendingConfirmations.value = []
    return
  }
  const preference = readPanelPreference(extension.pluginId)
  panelOpen.value = preference.open
  panelWidth.value = preference.width
  panelHeight.value = preference.height
  await nextTick()
  if (server) {
    // Server-mode UI: the runtime's own loopback server (e.g. the embedded
    // pi-web). No MessageChannel bridge and no sandbox: the page is a full
    // application that talks to its own origin.
    pendingConfirmations.value = []
    frameSrc.value = entryUrl
    return
  }
  const target = frame.value?.contentWindow
  if (!target) return
  bridge = createPluginFrameBridge({
    extension,
    placement: "floating-panel",
    instanceId: createPluginFrameInstanceId(),
    frameTarget: target as unknown as BridgeFrameTarget,
    router,
    route,
    locale: () => String(locale.value),
    onConfirmation: upsertConfirmation,
  })
  bridge.start()
  frameSrc.value = entryUrl
}

async function resolveConfirmation(decision: PluginConfirmationDecision) {
  const current = confirmation.value
  if (!current || confirmationBusy.value) return
  confirmationBusy.value = true
  confirmationError.value = ""
  try {
    const resolved = await pluginsApi.resolveConfirmation(current.ticketId, decision)
    if (confirmation.value?.ticketId === current.ticketId && resolved.state === decision) {
      pendingConfirmations.value = pendingConfirmations.value.filter((item) => item.ticketId !== current.ticketId)
    }
    else confirmationError.value = t("extensionHost.confirmation.failed")
  } catch {
    confirmationError.value = t("extensionHost.confirmation.failed")
  } finally {
    confirmationBusy.value = false
  }
}

function togglePanel() {
  panelOpen.value = !panelOpen.value
  saveOpenPreference()
}

function onLauncherClick(extension: PluginHostExtension) {
  if (activeExtension.value?.pluginId === extension.pluginId) {
    togglePanel()
    return
  }
  // Selecting a different plugin re-points the single panel/frame/bridge via the
  // activeExtension watcher; force it open so the click is always honoured, even
  // when that plugin's persisted preference was "closed".
  const preference = readPanelPreference(extension.pluginId)
  localStorage.setItem(
    preferenceKey(extension.pluginId),
    JSON.stringify({ open: true, width: preference.width, height: preference.height }),
  )
  selectedPluginId.value = extension.pluginId
}

function onShortcut(event: KeyboardEvent) {
  if (event.ctrlKey && event.shiftKey && !event.altKey && !event.metaKey && event.key.toLowerCase() === "a") {
    event.preventDefault()
    togglePanel()
  }
}

watch(
  () =>
    activeExtension.value
      ? `${activeExtension.value.pluginId}\u0000${activeExtension.value.ui.floatingPanel?.mode ?? "static"}\u0000${activeExtension.value.ui.floatingPanel?.entryUrl ?? ""}`
      : "",
  () => void activateExtension(activeExtension.value),
  { immediate: true },
)

watch(frame, (value) => {
  if (value && activeExtension.value && !bridge) void activateExtension(activeExtension.value)
})

onMounted(() => {
  window.addEventListener("keydown", onShortcut)
  window.addEventListener("resize", onViewportResize)
  void extensionsStore.ensureLoaded().then(refreshPendingConfirmations)
})

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onShortcut)
  window.removeEventListener("resize", onViewportResize)
  stopResize()
  disposeBridge()
})
</script>

<template>
  <div v-if="activeExtension" class="floating-extension-host" data-testid="floating-extension-host">
    <section
      v-show="panelOpen"
      class="floating-extension-panel"
      :style="panelStyle"
      :aria-label="activeExtension.displayName"
      data-testid="floating-extension-panel"
    >
      <button
        type="button"
        class="floating-extension-resize"
        :aria-label="t('extensionHost.resize')"
        data-testid="floating-extension-resize"
        @pointerdown="startResize"
        @keydown="resizeWithKeyboard"
      />
      <header class="floating-extension-header" aria-hidden="true" />
      <iframe
        ref="frame"
        class="floating-extension-frame"
        :src="frameSrc"
        :title="activeExtension.displayName"
        :sandbox="activeExtension && activeExtension.ui.floatingPanel?.mode === 'server' ? undefined : 'allow-scripts'"
        referrerpolicy="no-referrer"
      />
    </section>
    <div class="floating-extension-launchers">
      <button
        v-for="extension in floatingExtensions"
        :key="extension.pluginId"
        type="button"
        class="floating-extension-launcher"
        :class="{
          'is-open': panelOpen && activeExtension?.pluginId === extension.pluginId,
          'is-active': activeExtension?.pluginId === extension.pluginId,
        }"
        :title="extension.displayName"
        :aria-label="
          panelOpen && activeExtension?.pluginId === extension.pluginId
            ? t('extensionHost.minimize')
            : t('extensionHost.open', { name: extension.displayName })
        "
        :aria-expanded="panelOpen && activeExtension?.pluginId === extension.pluginId"
        data-testid="floating-extension-launcher"
        @click="onLauncherClick(extension)"
      >
        <img :src="agentIcon" alt="" aria-hidden="true" />
        <i v-if="extension.unreadCount" class="floating-extension-badge">{{
          extension.unreadCount > 9 ? "9+" : extension.unreadCount
        }}</i>
      </button>
    </div>
    <HostConfirmationLayer
      v-if="confirmation"
      :confirmation="confirmation"
      :plugin-name="activeExtension.displayName"
      :busy="confirmationBusy"
      :error="confirmationError"
      @resolve="resolveConfirmation"
    />
  </div>
</template>

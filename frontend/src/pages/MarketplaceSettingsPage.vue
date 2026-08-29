<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { Refresh } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import {
  pluginsApi,
  type MarketplaceEntry,
  type MarketplaceInstallOperation,
  type MarketplacePluginStatus,
} from "../api/plugins"
import { useExtensionsStore } from "../stores/extensions"
import { scheduleHostRefresh } from "../extensions/hostRefresh"

const props = withDefaults(defineProps<{ catalogEntries?: MarketplaceEntry[] }>(), {
  catalogEntries: () => [],
})
const { t } = useI18n()
const extensionsStore = useExtensionsStore()
const statuses = ref<MarketplacePluginStatus[]>([])
const liveCatalog = ref<MarketplaceEntry[]>([])
const selectedId = ref("")
const loading = ref(false)
const busyAction = ref("")
const error = ref("")

interface MarketplaceRecord {
  id: string
  entry?: MarketplaceEntry
  status: MarketplacePluginStatus
}

function emptyStatus(id: string): MarketplacePluginStatus {
  return {
    id,
    state: "not_installed",
    active_version: null,
    previous_version: null,
    enabled: false,
    installed_versions: [],
    reason: "",
    runtime_state: null,
    runtime_pid: null,
  }
}

const catalogUnavailable = computed(
  () => props.catalogEntries.length === 0 && liveCatalog.value.length === 0,
)

const records = computed<MarketplaceRecord[]>(() => {
  const effective = liveCatalog.value.length > 0 ? liveCatalog.value : props.catalogEntries
  const entries = new Map(effective.map((entry) => [entry.id, entry]))
  const states = new Map(statuses.value.map((status) => [status.id, status]))
  return [...new Set([...entries.keys(), ...states.keys()])]
    .sort((left, right) => (entries.get(left)?.name || left).localeCompare(entries.get(right)?.name || right))
    .map((id) => ({ id, entry: entries.get(id), status: states.get(id) ?? emptyStatus(id) }))
})
const selected = computed(() => records.value.find((record) => record.id === selectedId.value) ?? records.value[0] ?? null)
// The permission-approval bar has been removed: every declared permission is
// auto-approved, so install/enable always sends the full declared set.
const declaredPermissions = computed(() => selected.value?.entry?.permissions_summary ?? [])

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function updateStatus(status: MarketplacePluginStatus) {
  const index = statuses.value.findIndex((value) => value.id === status.id)
  if (index < 0) statuses.value.push(status)
  else statuses.value[index] = status
}

async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ""
  try {
    statuses.value = await pluginsApi.listMarketplacePlugins()
    try {
      liveCatalog.value = await pluginsApi.listMarketplaceCatalog()
    } catch {
      // A cold host (channel never polled) only has an empty catalog cache and
      // answers OFFLINE. Trigger the channel poll once before falling back to
      // the injected entries — otherwise a fresh install would show an empty
      // catalog forever and the user would never see the install action.
      try {
        await pluginsApi.refreshMarketplaceCatalog()
        liveCatalog.value = await pluginsApi.listMarketplaceCatalog()
      } catch {
        // The live catalog may be genuinely offline (MARKETPLACE_CATALOG_OFFLINE)
        // or the host may not ship one; fall back to the injected entries.
        liveCatalog.value = []
      }
    }
  } catch {
    statuses.value = []
    error.value = t("marketplace.loadFailed")
  } finally {
    loading.value = false
  }
}

async function confirmMutation(messageKey: string) {
  try {
    await ElMessageBox.confirm(t(messageKey), t("marketplace.confirmTitle"), {
      confirmButtonText: t("marketplace.confirm"),
      cancelButtonText: t("marketplace.cancel"),
      type: "warning",
    })
    return true
  } catch {
    return false
  }
}

async function runAction(action: string, operation: () => Promise<MarketplacePluginStatus>): Promise<boolean> {
  if (busyAction.value) return false
  busyAction.value = action
  error.value = ""
  try {
    updateStatus(await operation())
    await extensionsStore.refresh()
    ElMessage.success(t("marketplace.actionDone"))
    // Every lifecycle mutation changes what the floating plugin panel must
    // show (mount after enable, unmount after disable/uninstall, new entry
    // URL after restart/rollback); one host reload guarantees no stale state.
    scheduleHostRefresh()
    return true
  } catch (cause) {
    // Surface the reason as a toast too: the banner sits at the page top and
    // scrolls out of view, which read as "clicked, nothing happens".
    const message = cause instanceof Error && cause.message ? cause.message : t("marketplace.actionFailed")
    error.value = message
    ElMessage.error(message)
    return false
  } finally {
    busyAction.value = ""
  }
}

const installOp = ref<MarketplaceInstallOperation | null>(null)
const installAbort = ref<AbortController | null>(null)

// Enable/disable/restart/rollback/uninstall are synchronous host calls: the
// enable round-trip in particular waits for the plugin runtime to boot (up to
// its full startup timeout), which felt like the click doing nothing. Show an
// indeterminate progress strip with the action phase and an elapsed counter
// for every busy action that is not already covered by the install card.
const busyElapsed = ref(0)
let busyTimer: number | null = null
watch(busyAction, (value) => {
  if (busyTimer !== null) {
    window.clearInterval(busyTimer)
    busyTimer = null
  }
  if (value) {
    busyElapsed.value = 0
    busyTimer = window.setInterval(() => {
      busyElapsed.value += 1
    }, 1000)
  }
})

/** Follow an install operation to a terminal state.
 *
 * Primary path is the SSE stream; if the stream drops early (host restart,
 * proxy timeout) we keep polling the snapshot endpoint until it settles.
 */
async function followInstall(pluginId: string, operationId: string, signal: AbortSignal) {
  try {
    await pluginsApi.streamInstallOperation(pluginId, operationId, (snapshot) => {
      installOp.value = snapshot
    }, signal)
  } catch {
    // Stream broke early — the polling loop below takes over.
  }
  while (!signal.aborted && installOp.value?.state === "running") {
    await new Promise((resolve) => setTimeout(resolve, 1200))
    if (signal.aborted) return
    try {
      installOp.value = await pluginsApi.getInstallOperation(pluginId, operationId)
    } catch {
      // Keep polling through transient read errors.
    }
  }
}

function finishInstall() {
  const finalOp = installOp.value
  installOp.value = null
  if (finalOp?.state === "succeeded" && finalOp.status) {
    updateStatus(finalOp.status)
    void extensionsStore.refresh()
    ElMessage.success(t("marketplace.actionDone"))
    scheduleHostRefresh()
  } else if (finalOp?.state === "cancelled") {
    ElMessage.info(t("marketplace.installCancelled"))
  } else if (finalOp?.state === "failed") {
    const message = finalOp.errorMessage || t("marketplace.actionFailed")
    error.value = message
    // Toast the failure too: the banner sits at the page top and the failed
    // operation used to vanish without any visible signal ("clicked install,
    // nothing happens").
    ElMessage.error(message)
  }
}

async function install() {
  const record = selected.value
  if (!record?.entry || busyAction.value || !(await confirmMutation("marketplace.confirmInstall"))) return
  busyAction.value = "install"
  error.value = ""
  const controller = new AbortController()
  installAbort.value = controller
  try {
    const initial = await pluginsApi.installMarketplacePlugin(record.entry, declaredPermissions.value)
    installOp.value = initial
    await followInstall(record.id, initial.operationId, controller.signal)
    finishInstall()
    await load()
  } catch (cause) {
    const message = cause instanceof Error && cause.message ? cause.message : t("marketplace.actionFailed")
    error.value = message
    ElMessage.error(message)
  } finally {
    installAbort.value = null
    installOp.value = null
    busyAction.value = ""
  }
}

async function cancelInstall() {
  const record = selected.value
  const operation = installOp.value
  if (!record || !operation || operation.state !== "running") return
  installAbort.value?.abort()
  try {
    installOp.value = await pluginsApi.cancelInstallOperation(record.id, operation.operationId)
  } catch {
    try {
      installOp.value = await pluginsApi.getInstallOperation(record.id, operation.operationId)
    } catch {
      // Keep the last known state; the operation is terminal or about to be.
    }
  }
  finishInstall()
}

onBeforeUnmount(() => {
  installAbort.value?.abort()
  if (busyTimer !== null) {
    window.clearInterval(busyTimer)
    busyTimer = null
  }
})

async function enable() {
  const record = selected.value
  if (!record?.entry || !(await confirmMutation("marketplace.confirmEnable"))) return
  await runAction("enable", () => pluginsApi.enableMarketplacePlugin(record.id, declaredPermissions.value))
}

async function disable() {
  const record = selected.value
  if (!record || !(await confirmMutation("marketplace.confirmDisable"))) return
  await runAction("disable", () => pluginsApi.disableMarketplacePlugin(record.id))
}

async function restart() {
  const record = selected.value
  if (!record) return
  await runAction("restart", () => pluginsApi.restartMarketplacePlugin(record.id))
}

async function rollback() {
  const record = selected.value
  if (!record?.status.previous_version || !(await confirmMutation("marketplace.confirmRollback"))) return
  await runAction("rollback", () => pluginsApi.rollbackMarketplacePlugin(record.id, record.status.previous_version!))
}

async function uninstall() {
  const record = selected.value
  if (!record || !(await confirmMutation("marketplace.confirmUninstall"))) return
  // Success schedules the host reload inside runAction: the floating
  // panel/iframe can otherwise linger until a manual refresh, and no stale
  // plugin component may survive an uninstall.
  await runAction("uninstall", () => pluginsApi.uninstallMarketplacePlugin(record.id))
}

watch(
  records,
  (value) => {
    if (!value.some((record) => record.id === selectedId.value)) selectedId.value = value[0]?.id ?? ""
  },
  { immediate: true },
)
onMounted(() => void load())
</script>

<template>
  <section class="marketplace-page" aria-labelledby="marketplace-title">
    <header class="marketplace-header">
      <div>
        <h2 id="marketplace-title">{{ t("marketplace.title") }}</h2>
        <p>{{ t("marketplace.subtitle") }}</p>
      </div>
      <button type="button" class="icon-button" :aria-label="t('marketplace.refresh')" :disabled="loading" @click="load">
        <Refresh aria-hidden="true" />
      </button>
    </header>

    <p v-if="catalogUnavailable" class="marketplace-notice" role="status">{{ t("marketplace.catalogUnavailable") }}</p>
    <p v-if="error" class="marketplace-error" role="alert">{{ error }}</p>
    <div v-if="loading" class="marketplace-loading" aria-live="polite">{{ t("marketplace.loading") }}</div>
    <div v-else-if="records.length === 0" class="marketplace-empty">{{ t("marketplace.empty") }}</div>
    <div v-else class="marketplace-workspace">
      <nav class="marketplace-list" :aria-label="t('marketplace.pluginList')">
        <button
          v-for="record in records"
          :key="record.id"
          type="button"
          class="marketplace-list-item"
          :class="{ active: selected?.id === record.id }"
          @click="selectedId = record.id"
        >
          <span>
            <strong>{{ record.entry?.name || record.id }}</strong>
            <small>{{ record.entry?.publisher_id || t("marketplace.publisherUnknown") }}</small>
          </span>
          <i :data-state="record.status.state">{{ t(`marketplace.state.${record.status.state}`) }}</i>
        </button>
      </nav>

      <article v-if="selected" class="marketplace-detail">
        <header>
          <div>
            <h3>{{ selected.entry?.name || selected.id }}</h3>
            <p>{{ selected.entry?.description || t("marketplace.metadataUnavailable") }}</p>
          </div>
          <span class="marketplace-version">{{ selected.status.active_version || selected.entry?.latest_version || "-" }}</span>
        </header>

        <dl class="marketplace-metadata">
          <div><dt>{{ t("marketplace.publisher") }}</dt><dd>{{ selected.entry?.publisher_id || "-" }}</dd></div>
          <div><dt>{{ t("marketplace.version") }}</dt><dd>{{ selected.entry?.latest_version || selected.status.active_version || "-" }}</dd></div>
          <div><dt>{{ t("marketplace.license") }}</dt><dd>{{ selected.entry?.license || "-" }}</dd></div>
          <div><dt>{{ t("marketplace.size") }}</dt><dd>{{ selected.entry ? formatBytes(selected.entry.package_size) : "-" }}</dd></div>
          <div><dt>{{ t("marketplace.compatibility") }}</dt><dd>{{ selected.entry?.host_compatibility || "-" }}</dd></div>
          <div><dt>{{ t("marketplace.platforms") }}</dt><dd>{{ selected.entry?.platforms.join(", ") || "-" }}</dd></div>
        </dl>

        <div v-if="installOp" class="marketplace-install-progress" aria-live="polite">
          <div class="marketplace-install-progress-head">
            <span>{{ t(`marketplace.phase.${installOp.phase}`) }}</span>
            <span v-if="installOp.progress.total > 0">
              {{ formatBytes(installOp.progress.current) }} / {{ formatBytes(installOp.progress.total) }}
            </span>
          </div>
          <el-progress
            v-if="installOp.state === 'running'"
            :percentage="installOp.progress.percent ?? 0"
            :stroke-width="8"
          />
          <p v-if="installOp.state === 'failed' && installOp.errorMessage" class="marketplace-error" role="alert">
            {{ installOp.errorMessage }}
          </p>
          <div v-if="installOp.state === 'running'" class="marketplace-install-progress-actions">
            <button type="button" class="secondary-action" @click="cancelInstall">
              {{ t("marketplace.cancelInstall") }}
            </button>
          </div>
        </div>

        <div v-else-if="busyAction" class="marketplace-install-progress" role="status" aria-live="polite" data-test="busy-progress">
          <div class="marketplace-install-progress-head">
            <span>{{ t(`marketplace.busy.${busyAction}`) }}</span>
            <span>{{ t("marketplace.elapsed", { seconds: busyElapsed }) }}</span>
          </div>
          <div class="marketplace-busy-bar" aria-hidden="true"><i></i></div>
        </div>

        <p v-if="selected.status.reason" class="marketplace-error" role="alert">{{ t("marketplace.statusError") }}</p>
        <footer class="marketplace-actions">
          <button
            v-if="selected.status.state === 'not_installed'"
            type="button"
            class="primary-action"
            :disabled="!selected.entry || Boolean(busyAction)"
            @click="install"
          >{{ t("marketplace.install") }}</button>
          <button
            v-if="selected.status.state === 'installed' || selected.status.state === 'broken'"
            type="button"
            class="primary-action"
            :disabled="!selected.entry || Boolean(busyAction)"
            @click="enable"
          >{{ t("marketplace.enable") }}</button>
          <button
            v-if="selected.status.enabled"
            type="button"
            class="secondary-action"
            :disabled="Boolean(busyAction)"
            @click="disable"
          >{{ t("marketplace.disable") }}</button>
          <button
            v-if="selected.status.state === 'runtime_error'"
            type="button"
            class="secondary-action"
            :disabled="Boolean(busyAction)"
            @click="restart"
          >{{ t("marketplace.restart") }}</button>
          <button
            v-if="selected.status.previous_version"
            type="button"
            class="secondary-action"
            :disabled="Boolean(busyAction)"
            @click="rollback"
          >{{ t("marketplace.rollback") }}</button>
          <button
            v-if="selected.status.state !== 'not_installed'"
            type="button"
            class="danger-action"
            :disabled="Boolean(busyAction)"
            @click="uninstall"
          >{{ t("marketplace.uninstall") }}</button>
        </footer>
      </article>
    </div>
  </section>
</template>

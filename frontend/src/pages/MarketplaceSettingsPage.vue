<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { Refresh } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import {
  pluginsApi,
  type MarketplaceEntry,
  type MarketplacePluginStatus,
} from "../api/plugins"
import { useExtensionsStore } from "../stores/extensions"

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
const approvedByPlugin = reactive<Record<string, string[]>>({})

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
const selectedPermissions = computed(() => (selected.value ? (approvedByPlugin[selected.value.id] ?? []) : []))
// A plugin that declares no permissions requires no approval and is
// installable immediately ([].every() is vacuously true).
const allPermissionsApproved = computed(() => {
  const required = selected.value?.entry?.permissions_summary ?? []
  return required.every((permission) => selectedPermissions.value.includes(permission))
})

function permissionLabel(permission: string) {
  const key = `marketplace.permissions.${permission}`
  const translated = t(key)
  return translated === key ? permission : translated
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function togglePermission(pluginId: string, permission: string, checked: boolean) {
  const current = new Set(approvedByPlugin[pluginId] ?? [])
  if (checked) current.add(permission)
  else current.delete(permission)
  approvedByPlugin[pluginId] = [...current]
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
    const [installed, catalog] = await Promise.all([
      pluginsApi.listMarketplacePlugins(),
      // The live catalog may be offline (MARKETPLACE_CATALOG_OFFLINE) or the
      // host may not ship one; fall back to the injected entries when empty.
      pluginsApi.listMarketplaceCatalog().catch(() => [] as MarketplaceEntry[]),
    ])
    statuses.value = installed
    liveCatalog.value = catalog
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

async function runAction(action: string, operation: () => Promise<MarketplacePluginStatus>) {
  if (busyAction.value) return
  busyAction.value = action
  error.value = ""
  try {
    updateStatus(await operation())
    await extensionsStore.refresh()
    ElMessage.success(t("marketplace.actionDone"))
  } catch {
    error.value = t("marketplace.actionFailed")
  } finally {
    busyAction.value = ""
  }
}

async function install() {
  const record = selected.value
  if (!record?.entry || !allPermissionsApproved.value || !(await confirmMutation("marketplace.confirmInstall"))) return
  await runAction("install", () => pluginsApi.installMarketplacePlugin(record.entry!, selectedPermissions.value))
}

async function enable() {
  const record = selected.value
  if (!record?.entry || !allPermissionsApproved.value || !(await confirmMutation("marketplace.confirmEnable"))) return
  await runAction("enable", () => pluginsApi.enableMarketplacePlugin(record.id, selectedPermissions.value))
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

        <fieldset v-if="selected.entry?.permissions_summary.length" class="marketplace-permissions">
          <legend>{{ t("marketplace.permissionsTitle") }}</legend>
          <label v-for="permission in selected.entry.permissions_summary" :key="permission">
            <input
              type="checkbox"
              :checked="selectedPermissions.includes(permission)"
              @change="togglePermission(selected.id, permission, ($event.target as HTMLInputElement).checked)"
            >
            <span><strong>{{ permissionLabel(permission) }}</strong><small>{{ permission }}</small></span>
          </label>
        </fieldset>

        <p v-if="selected.status.reason" class="marketplace-error" role="alert">{{ t("marketplace.statusError") }}</p>
        <footer class="marketplace-actions">
          <button
            v-if="selected.status.state === 'not_installed'"
            type="button"
            class="primary-action"
            :disabled="!selected.entry || !allPermissionsApproved || Boolean(busyAction)"
            @click="install"
          >{{ t("marketplace.install") }}</button>
          <button
            v-if="selected.status.state === 'installed' || selected.status.state === 'broken'"
            type="button"
            class="primary-action"
            :disabled="!selected.entry || !allPermissionsApproved || Boolean(busyAction)"
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

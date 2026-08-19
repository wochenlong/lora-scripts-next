<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import { ElMessage, ElMessageBox } from "element-plus"
import { Refresh, Search } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import { productsApi, type Product, type ProductDetail, type ProductGroup } from "../api/products"
import { copyText } from "../utils/clipboard"
import { moduleForTrainType } from "../training/modules"
import PathPickerDialog from "../components/PathPickerDialog.vue"
import { useServerPathPick } from "../composables/useServerPathPick"

const { t } = useI18n()
const router = useRouter()

const groups = ref<ProductGroup[]>([])
const families = ref<string[]>([])
const scannedDirs = ref<string[]>([])
const deployTargets = ref<Record<string, string>>({})
const activeFamily = ref("")
const loading = ref(false)
const scanning = ref(false)
const reconciling = ref(false)
const scanOpen = ref(false)
const scanDir = ref("")

const detailOpen = ref(false)
const detailLoading = ref(false)
const detail = ref<ProductDetail | null>(null)
const deployTarget = ref("")
const deployMethod = ref<"copy" | "link">("copy")
const deployBusy = ref(false)
const newTargetName = ref("")
const newTargetPath = ref("")

const {
  open: pickerOpen,
  mode: pickerMode,
  initialPath: pickerInitialPath,
  nameFilter: pickerNameFilter,
  pick,
  onConfirm: onPickerConfirm,
  onCancel: onPickerCancel,
} = useServerPathPick()

const totalCount = computed(() => groups.value.reduce((n, g) => n + g.products.length, 0))
const targetNames = computed(() => Object.keys(deployTargets.value))

async function load() {
  loading.value = true
  try {
    const data = await productsApi.list(activeFamily.value || undefined)
    groups.value = data.groups
    families.value = data.families
    scannedDirs.value = data.scanned_dirs
    deployTargets.value = data.deploy_targets ?? {}
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : t("products.msg.loadFail"))
  } finally {
    loading.value = false
  }
}

async function scan() {
  scanning.value = true
  try {
    const dirs = scanDir.value.trim() ? [scanDir.value.trim()] : []
    const data = await productsApi.scan(dirs)
    ElMessage.success(t("products.total", { n: data.total }))
    scanOpen.value = false
    scanDir.value = ""
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : t("products.msg.scanFail"))
  } finally {
    scanning.value = false
  }
}

async function pickFor(purpose: "scan" | "target") {
  const path = await pick({ mode: "folder", initialPath: purpose === "scan" ? scanDir.value : newTargetPath.value })
  if (!path) return
  if (purpose === "scan") scanDir.value = path
  else newTargetPath.value = path
}

async function openDetail(product: Product) {
  detailOpen.value = true
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = (await productsApi.detail(product.id)).product
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : t("products.msg.detailFail"))
    detailOpen.value = false
  } finally {
    detailLoading.value = false
  }
}

function deployStatusText(status: string | undefined): string {
  if (!status) return ""
  const key = `products.deploy.status.${status}` as const
  const text = t(key)
  return text === key ? status : text
}

function isConflict(status: string | undefined): boolean {
  return status === "conflict"
}

async function refreshDetail() {
  if (!detail.value) return
  detail.value = (await productsApi.detail(detail.value.id)).product
}

async function deployCurrent() {
  if (!detail.value || !deployTarget.value) return
  deployBusy.value = true
  try {
    await productsApi.deploy(detail.value.id, deployTarget.value, deployMethod.value)
    ElMessage.success(t("products.deploy.status.deployed"))
    await refreshDetail()
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : t("products.deploy.msg.deployFail"))
  } finally {
    deployBusy.value = false
  }
}

async function undeployCurrent(target: string) {
  if (!detail.value) return
  deployBusy.value = true
  try {
    await productsApi.undeploy(detail.value.id, target)
    ElMessage.success(t("products.deploy.status.removed"))
    await refreshDetail()
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : t("products.deploy.msg.undeployFail"))
  } finally {
    deployBusy.value = false
  }
}

async function addTarget() {
  if (!newTargetName.value.trim() || !newTargetPath.value.trim()) return
  try {
    const data = await productsApi.addDeployTarget(newTargetName.value.trim(), newTargetPath.value.trim())
    deployTargets.value = data.targets
    newTargetName.value = ""
    newTargetPath.value = ""
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : t("products.deploy.msg.targetFail"))
  }
}

async function removeTarget(name: string) {
  try {
    const data = await productsApi.removeDeployTarget(name)
    deployTargets.value = data.targets
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : t("products.deploy.msg.targetFail"))
  }
}

async function reconcileNow() {
  reconciling.value = true
  try {
    const data = await productsApi.reconcile()
    const problems = data.results.filter((r) => r.status === "conflict" || r.status === "error")
    if (problems.length) {
      ElMessage.warning(problems.map((r) => `${r.target}: ${r.message || r.status}`).join("\n"))
    } else {
      ElMessage.success(t("products.deploy.reconcileDone"))
    }
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : t("products.deploy.msg.deployFail"))
  } finally {
    reconciling.value = false
  }
}

async function deleteCurrent() {
  if (!detail.value) return
  try {
    await ElMessageBox.confirm(
      t("products.deploy.deleteConfirm", { name: detail.value.name }),
      t("products.deploy.deleteAction"),
      { type: "warning" },
    )
  } catch {
    return
  }
  deployBusy.value = true
  try {
    await productsApi.remove(detail.value.id)
    detailOpen.value = false
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : t("products.deploy.msg.deleteFail"))
  } finally {
    deployBusy.value = false
  }
}

async function copyPath(path: string) {
  try {
    await copyText(path)
    ElMessage.success(t("products.copied"))
  } catch {
    ElMessage.error(path)
  }
}

function formatSize(size: number | null): string {
  if (size == null) return t("products.sizeUnknown")
  if (size >= 1 << 30) return `${(size / (1 << 30)).toFixed(2)} GB`
  if (size >= 1 << 20) return `${(size / (1 << 20)).toFixed(1)} MB`
  return `${(size / 1024).toFixed(0)} KB`
}

function formatTime(mtime: number | null): string {
  if (mtime == null) return "—"
  return new Date(mtime * 1000).toLocaleString()
}

function versionLabel(product: Product): string {
  if (product.epoch != null) return t("products.epochLabel", { n: product.epoch })
  if (product.step != null) return t("products.stepLabel", { n: product.step })
  return t("products.finalLabel")
}

const metadataEntries = computed(() => Object.entries(detail.value?.metadata ?? {}))

// ---- F11: refill the training form from a product ----

const refillBusy = ref(false)

async function refillTraining() {
  const product = detail.value
  if (!product) return
  refillBusy.value = true
  try {
    const { config } = await productsApi.trainingConfig(product.id)
    // Reuse the import pipeline: TrainingPage picks this up, runs
    // validate-import and hydrates the form.
    sessionStorage.setItem("mikazuki-pending-import", JSON.stringify(config))
    const module_ = moduleForTrainType(String(config.model_train_type || ""))
    if (module_) {
      await router.push({ path: "/training", query: { model: module_.model, engine: module_.engine, target: module_.target } })
    } else {
      await router.push("/training")
    }
    detailOpen.value = false
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : t("products.refill.fail"))
  } finally {
    refillBusy.value = false
  }
}

const metaEditing = ref(false)
const metaDraft = ref<{ key: string; value: string }[]>([])
const metaSaving = ref(false)

function startMetaEdit() {
  metaDraft.value = Object.entries(detail.value?.metadata ?? {}).map(([key, value]) => ({ key, value }))
  metaEditing.value = true
}

function addMetaRow() {
  metaDraft.value.push({ key: "", value: "" })
}

function removeMetaRow(index: number) {
  metaDraft.value.splice(index, 1)
}

async function saveMetadata() {
  if (!detail.value) return
  metaSaving.value = true
  try {
    const metadata: Record<string, string> = {}
    for (const row of metaDraft.value) {
      const key = row.key.trim()
      if (key) metadata[key] = row.value
    }
    await productsApi.updateMetadata(detail.value.id, metadata)
    ElMessage.success(t("products.detailDialog.metaSaved"))
    metaEditing.value = false
    await refreshDetail()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : t("products.detailDialog.metaSaveFail"))
  } finally {
    metaSaving.value = false
  }
}

const LARGE_DOWNLOAD_BYTES = 500 * 1024 * 1024

async function downloadProduct(product: Product) {
  if ((product.size ?? 0) > LARGE_DOWNLOAD_BYTES) {
    try {
      await ElMessageBox.confirm(
        t("products.detailDialog.downloadLargeHint", { size: formatSize(product.size) }),
        t("products.detailDialog.download"),
        { type: "warning" },
      )
    } catch {
      return
    }
  }
  window.open(productsApi.downloadUrl(product.id), "_blank")
}

// ---- product actions (resize / merge / extract) ----

const actionOpen = ref(false)
const actionProduct = ref<Product | null>(null)
const actionKind = ref<"resize" | "merge" | "extract">("resize")
const actionOutput = ref("")
const actionBusy = ref(false)
const newRank = ref<number | null>(null)
const newConvRank = ref<number | null>(null)
const dynamicMethod = ref("")
const dynamicParam = ref<number | null>(null)
const mergeOther = ref("")
const ratioSelf = ref(1)
const ratioOther = ref(1)
const mergeConcat = ref(false)
const extractBase = ref("")
const extractDim = ref(32)

const actionBlockedReason = computed(() => {
  const product = actionProduct.value
  if (!product) return ""
  if (product.train_type && product.train_type.includes("musubi")) return t("products.actions.musubiBlocked")
  if (actionKind.value === "resize" && product.is_lycoris) return t("products.actions.lokrBlocked")
  return ""
})

const otherProducts = computed(() =>
  groups.value.flatMap((g) => g.products)
    .filter((p) => p.status === "present" && p.id !== actionProduct.value?.id),
)

function openAction(product: Product) {
  actionProduct.value = product
  actionKind.value = product.is_lycoris ? "merge" : "resize"
  actionOutput.value = `${product.path.replace(/\.[^.]+$/, "")}-derived.safetensors`
  mergeOther.value = ""
  actionOpen.value = true
}

async function submitAction() {
  const product = actionProduct.value
  const output = actionOutput.value.trim()
  if (!product || !output) return
  actionBusy.value = true
  try {
    if (actionKind.value === "resize") {
      await productsApi.resize(product.id, {
        output_path: output,
        new_rank: newRank.value,
        new_conv_rank: newConvRank.value,
        dynamic_method: dynamicMethod.value || null,
        dynamic_param: dynamicParam.value,
      })
    } else if (actionKind.value === "merge") {
      if (!mergeOther.value) throw new Error(t("products.actions.otherProduct"))
      await productsApi.merge({
        inputs: [product.id, mergeOther.value],
        ratios: [ratioSelf.value, ratioOther.value],
        output_path: output,
        concat: mergeConcat.value,
      })
    } else {
      if (!extractBase.value.trim()) throw new Error(t("products.actions.baseModelPath"))
      await productsApi.extract(product.id, {
        model_org: extractBase.value.trim(),
        output_path: output,
        dim: extractDim.value,
      })
    }
    ElMessage.success(t("products.actions.submitted"))
    actionOpen.value = false
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : t("products.actions.submitFail"))
  } finally {
    actionBusy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="products-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">{{ t("nav.manage") }}</p>
        <h1>{{ t("products.title") }}</h1>
        <p class="page-subtitle">{{ t("products.subtitle") }}</p>
      </div>
      <div class="header-actions">
        <el-button :icon="Search" @click="scanOpen = true">{{ t("products.scan") }}</el-button>
        <el-button :loading="reconciling" @click="reconcileNow">{{ t("products.deploy.reconcile") }}</el-button>
        <el-button :icon="Refresh" :loading="loading" @click="load">{{ t("products.refresh") }}</el-button>
      </div>
    </header>

    <nav v-if="families.length > 1" class="family-tabs">
      <button class="family-tab" :class="{ active: activeFamily === '' }" @click="activeFamily = ''; load()">
        {{ t("products.title") }}
      </button>
      <button
        v-for="family in families"
        :key="family"
        class="family-tab"
        :class="{ active: activeFamily === family }"
        @click="activeFamily = family; load()"
      >
        {{ family }}
      </button>
    </nav>

    <p v-if="totalCount > 0" class="products-total">{{ t("products.total", { n: totalCount }) }}</p>

    <div v-if="!loading && totalCount === 0" class="products-empty">{{ t("products.empty") }}</div>

    <section v-for="group in groups" :key="group.key" class="product-group">
      <header class="group-header">
        <div class="group-title">
          <strong>{{ group.name }}</strong>
          <span class="group-meta">{{ group.family }} · {{ t("products.epochs", { n: group.products.length }) }}</span>
          <RouterLink v-if="group.run_task_id" class="group-run" :to="`/tasks`">
            {{ group.train_type || group.run_task_id }}
          </RouterLink>
          <span v-else class="group-meta">{{ t("products.noRun") }}</span>
        </div>
        <button class="group-path" :title="t('products.copyPath')" @click="copyPath(group.output_dir)">
          {{ group.output_dir }}
        </button>
      </header>
      <table class="product-table">
        <thead>
          <tr>
            <th>{{ t("products.columns.name") }}</th>
            <th>{{ t("products.columns.size") }}</th>
            <th>{{ t("products.columns.mtime") }}</th>
            <th>{{ t("products.columns.dimAlpha") }}</th>
            <th>{{ t("products.columns.baseModel") }}</th>
            <th>{{ t("products.columns.status") }}</th>
            <th>{{ t("products.columns.actions") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="product in group.products" :key="product.id" :class="{ 'is-missing': product.status === 'missing' }">
            <td>
              <span class="product-name">{{ product.name }}</span>
              <span class="product-version">{{ versionLabel(product) }}</span>
            </td>
            <td>{{ formatSize(product.size) }}</td>
            <td>{{ formatTime(product.mtime) }}</td>
            <td>
              <template v-if="product.dim != null">
                {{ t("products.dimAlpha", { dim: product.dim, alpha: product.alpha ?? "—" }) }}
              </template>
              <template v-else>—</template>
            </td>
            <td>{{ product.base_model_version || product.sd_model_name || "—" }}</td>
            <td>
              <span v-if="product.status === 'missing'" class="status-missing" :title="t('products.missingHint')">
                {{ t("products.missing") }}
              </span>
              <span
                v-for="(status, target) in product.deploy_status ?? {}"
                v-show="!target.endsWith('__message')"
                :key="target"
                class="deploy-badge"
                :class="{ 'deploy-conflict': isConflict(status) }"
                :title="isConflict(status) ? (product.deploy_status?.[`${target}__message`] || t('products.deploy.conflictHint')) : target"
              >
                {{ target }}: {{ deployStatusText(status) }}
              </span>
            </td>
            <td class="row-actions">
              <el-button size="small" @click="openDetail(product)">{{ t("products.detail") }}</el-button>
              <el-button size="small" @click="copyPath(product.path)">{{ t("products.copyPath") }}</el-button>
              <el-button v-if="product.status === 'present'" size="small" @click="openAction(product)">
                {{ t("products.actions.actionLabel") }}
              </el-button>
              <el-button v-if="product.status === 'present'" size="small" @click="downloadProduct(product)">
                {{ t("products.detailDialog.download") }}
              </el-button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <el-dialog v-model="scanOpen" :title="t('products.scanTitle')" width="520px">
      <p class="dialog-hint">{{ t("products.scanHint") }}</p>
      <label class="dialog-label">{{ t("products.scanDirLabel") }}</label>
      <div class="scan-input-row">
        <el-input v-model="scanDir" :placeholder="t('products.scanDirPlaceholder')" />
        <el-button @click="pickFor('scan')">{{ t("products.browse") }}</el-button>
      </div>
      <template #footer>
        <el-button @click="scanOpen = false">{{ t("training.submitConfirm.cancel") }}</el-button>
        <el-button type="primary" :loading="scanning" @click="scan">{{ t("products.scan") }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailOpen" :title="t('products.detailDialog.title')" width="720px">
      <div v-loading="detailLoading" class="product-detail">
        <template v-if="detail">
          <div class="detail-row">
            <span class="detail-label">{{ t("products.detailDialog.path") }}</span>
            <button class="group-path" :title="t('products.copyPath')" @click="copyPath(detail.path)">{{ detail.path }}</button>
          </div>
          <div v-if="detail.run" class="detail-run">
            <span class="detail-label">{{ t("products.detailDialog.runInfo") }}</span>
            <span>{{ detail.run.train_type }} · {{ detail.run.task_id }}</span>
            <a :href="`/train-log?task_id=${detail.run.task_id}`" target="_blank" rel="noreferrer">
              {{ t("products.detailDialog.taskLog") }}
            </a>
            <div class="detail-row">
              <span class="detail-label">{{ t("products.detailDialog.configSnapshot") }}</span>
              <span v-if="detail.run.config_exists">{{ detail.run.config_path }}</span>
              <span v-else class="status-missing">{{ t("products.detailDialog.configMissing") }}</span>
            </div>
          </div>
          <div class="detail-deploy">
            <span class="detail-label">{{ t("products.deploy.title") }}</span>
            <div v-if="Object.keys(detail.deployed_to ?? {}).length" class="deploy-entries">
              <div v-for="(entry, target) in detail.deployed_to" :key="target" class="deploy-entry">
                <span class="deploy-target-name">{{ target }}</span>
                <span
                  class="deploy-badge"
                  :class="{ 'deploy-conflict': isConflict(detail.deploy_status?.[target]) }"
                  :title="detail.deploy_status?.[`${target}__message`] || ''"
                >{{ deployStatusText(detail.deploy_status?.[target]) }}</span>
                <span class="group-meta">{{ entry.path }}</span>
                <el-button
                  size="small"
                  :disabled="deployBusy"
                  @click="undeployCurrent(target)"
                >{{ t("products.deploy.undeployAction") }}</el-button>
              </div>
            </div>
            <div class="deploy-form">
              <el-select v-model="deployTarget" :placeholder="t('products.deploy.targetLabel')" size="small">
                <el-option v-for="name in targetNames" :key="name" :label="`${name} (${deployTargets[name]})`" :value="name" />
              </el-select>
              <el-select v-model="deployMethod" size="small">
                <el-option value="copy" :label="t('products.deploy.methodCopy')" />
                <el-option value="link" :label="t('products.deploy.methodLink')" />
              </el-select>
              <el-button
                size="small"
                type="primary"
                :disabled="deployBusy || !deployTarget || detail.status !== 'present'"
                :loading="deployBusy"
                @click="deployCurrent"
              >{{ t("products.deploy.deployAction") }}</el-button>
            </div>
            <div class="deploy-target-admin">
              <p v-if="targetNames.length === 0" class="dialog-hint">{{ t("products.deploy.targetEmpty") }}</p>
              <div v-for="name in targetNames" :key="name" class="deploy-target-row">
                <span class="deploy-target-name">{{ name }}</span>
                <span class="group-meta">{{ deployTargets[name] }}</span>
                <el-button size="small" text @click="removeTarget(name)">×</el-button>
              </div>
              <div class="deploy-target-row">
                <el-input v-model="newTargetName" size="small" :placeholder="t('products.deploy.targetNamePlaceholder')" />
                <el-input v-model="newTargetPath" size="small" :placeholder="t('products.deploy.targetPathPlaceholder')" />
                <el-button size="small" @click="pickFor('target')">{{ t("products.browse") }}</el-button>
                <el-button size="small" :disabled="!newTargetName.trim() || !newTargetPath.trim()" @click="addTarget">
                  {{ t("products.deploy.addTarget") }}
                </el-button>
              </div>
            </div>
          </div>
          <div class="detail-danger">
            <el-button size="small" :loading="refillBusy" @click="refillTraining">
              {{ t("products.refill.action") }}
            </el-button>
            <el-button size="small" type="danger" plain :disabled="deployBusy" @click="deleteCurrent">
              {{ t("products.deploy.deleteAction") }}
            </el-button>
          </div>
          <div class="detail-metadata">
            <div class="detail-metadata-header">
              <span class="detail-label">{{ t("products.detailDialog.metadata") }}</span>
              <div v-if="!metaEditing" class="row-actions">
                <el-button v-if="detail.status === 'present'" size="small" @click="downloadProduct(detail)">
                  {{ t("products.detailDialog.download") }}
                </el-button>
                <el-button v-if="detail.status === 'present'" size="small" @click="startMetaEdit">
                  {{ t("products.detailDialog.editMeta") }}
                </el-button>
              </div>
              <div v-else class="row-actions">
                <el-button size="small" @click="addMetaRow">{{ t("products.detailDialog.addKey") }}</el-button>
                <el-button size="small" type="primary" :loading="metaSaving" @click="saveMetadata">
                  {{ t("products.detailDialog.saveMeta") }}
                </el-button>
                <el-button size="small" @click="metaEditing = false">{{ t("products.detailDialog.cancelEdit") }}</el-button>
              </div>
            </div>
            <p v-if="metadataEntries.length === 0 && !metaEditing" class="dialog-hint">{{ t("products.detailDialog.metadataEmpty") }}</p>
            <table v-if="!metaEditing && metadataEntries.length > 0" class="metadata-table">
              <tbody>
                <tr v-for="[key, value] in metadataEntries" :key="key">
                  <td class="metadata-key">{{ key }}</td>
                  <td class="metadata-value">{{ value }}</td>
                </tr>
              </tbody>
            </table>
            <div v-if="metaEditing" class="metadata-edit">
              <div v-for="(row, index) in metaDraft" :key="index" class="metadata-edit-row">
                <el-input v-model="row.key" size="small" :placeholder="t('products.detailDialog.keyPlaceholder')" />
                <el-input v-model="row.value" size="small" :placeholder="t('products.detailDialog.valuePlaceholder')" />
                <el-button size="small" text :aria-label="t('products.detailDialog.removeKey')" @click="removeMetaRow(index)">×</el-button>
              </div>
            </div>
          </div>
        </template>
      </div>
    </el-dialog>

    <el-dialog v-model="actionOpen" :title="t('products.actions.title')" width="560px">
      <div v-if="actionProduct" class="action-form">
        <p class="dialog-hint">{{ actionProduct.name }}</p>
        <label class="dialog-label">{{ t("products.actions.actionLabel") }}</label>
        <el-select v-model="actionKind">
          <el-option value="resize" :label="t('products.actions.resize')" />
          <el-option value="merge" :label="t('products.actions.merge')" />
          <el-option value="extract" :label="t('products.actions.extract')" />
        </el-select>

        <p v-if="actionBlockedReason" class="action-blocked">{{ actionBlockedReason }}</p>
        <template v-else>
          <template v-if="actionKind === 'resize'">
            <label class="dialog-label">{{ t("products.actions.newRank") }}</label>
            <el-input-number v-model="newRank" :min="1" :max="1024" />
            <label class="dialog-label">{{ t("products.actions.convRank") }}</label>
            <el-input-number v-model="newConvRank" :min="1" :max="1024" />
            <label class="dialog-label">{{ t("products.actions.dynamicMethod") }}</label>
            <el-select v-model="dynamicMethod" clearable :placeholder="t('products.actions.dynamicOff')">
              <el-option value="sv_ratio" label="sv_ratio" />
              <el-option value="sv_fro" label="sv_fro" />
              <el-option value="sv_cumulative" label="sv_cumulative" />
            </el-select>
            <template v-if="dynamicMethod">
              <label class="dialog-label">{{ t("products.actions.dynamicParam") }}</label>
              <el-input-number v-model="dynamicParam" :min="0" :max="1" :step="0.05" />
            </template>
          </template>

          <template v-else-if="actionKind === 'merge'">
            <label class="dialog-label">{{ t("products.actions.otherProduct") }}</label>
            <el-select v-model="mergeOther" filterable>
              <el-option v-for="p in otherProducts" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
            <label class="dialog-label">{{ t("products.actions.ratioSelf") }}</label>
            <el-input-number v-model="ratioSelf" :min="0" :max="1" :step="0.1" />
            <label class="dialog-label">{{ t("products.actions.ratioOther") }}</label>
            <el-input-number v-model="ratioOther" :min="0" :max="1" :step="0.1" />
            <label class="check-row"><input v-model="mergeConcat" type="checkbox" /> {{ t("products.actions.concat") }}</label>
          </template>

          <template v-else>
            <label class="dialog-label">{{ t("products.actions.baseModelPath") }}</label>
            <el-input v-model="extractBase" placeholder="/path/to/base.safetensors" />
            <label class="dialog-label">{{ t("products.actions.dim") }}</label>
            <el-input-number v-model="extractDim" :min="1" :max="1024" />
          </template>

          <label class="dialog-label">{{ t("products.actions.outputPath") }}</label>
          <el-input v-model="actionOutput" />
          <p class="dialog-hint">{{ t("products.actions.outputHint") }}</p>
        </template>
      </div>
      <template #footer>
        <el-button @click="actionOpen = false">{{ t("training.submitConfirm.cancel") }}</el-button>
        <el-button
          type="primary"
          :loading="actionBusy"
          :disabled="!!actionBlockedReason || !actionOutput.trim()"
          @click="submitAction"
        >{{ t("products.actions.submit") }}</el-button>
      </template>
    </el-dialog>

    <PathPickerDialog
      v-model="pickerOpen"
      :mode="pickerMode"
      :initial-path="pickerInitialPath"
      :name-filter="pickerNameFilter"
      @confirm="onPickerConfirm"
      @cancel="onPickerCancel"
    />
  </div>
</template>

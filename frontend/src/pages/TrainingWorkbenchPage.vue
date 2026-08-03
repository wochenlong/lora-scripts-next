<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { useI18n } from "vue-i18n"
import AnimaFastPage from "./AnimaFastPage.vue"
import TrainingPage from "./TrainingPage.vue"
import TrainingSelector from "../components/TrainingSelector.vue"
import WorkbenchHeader from "../components/WorkbenchHeader.vue"
import {
  DEFAULT_SELECTION,
  SCHEMA_META,
  TRAINING_ENGINES,
  TRAINING_TARGETS,
  firstSupportedEngine,
  firstSupportedTarget,
  isEngineSupported,
  isTargetSupported,
  moduleForSchema,
  normalizeModel,
  resolveModule,
  type TrainingEngine,
  type TrainingModel,
  type TrainingTarget,
} from "../training/modules"

interface TrainingChildActions {
  saveConfig?: () => void
  openImport?: () => void
  resetConfig?: () => void
}

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const model = ref<TrainingModel>(DEFAULT_SELECTION.model)
const engine = ref<TrainingEngine>(DEFAULT_SELECTION.engine)
const target = ref<TrainingTarget>(DEFAULT_SELECTION.target)
const childRef = ref<TrainingChildActions>()

function isEngine(value: unknown): value is TrainingEngine { return TRAINING_ENGINES.includes(value as TrainingEngine) }
function isTarget(value: unknown): value is TrainingTarget { return TRAINING_TARGETS.includes(value as TrainingTarget) }

function initFromQuery() {
  const query = route.query
  const fromSchema = typeof query.schema === "string" ? moduleForSchema(query.schema) : undefined
  if (fromSchema) {
    model.value = fromSchema.model
    engine.value = fromSchema.engine
    target.value = fromSchema.target
    return
  }
  const normalized = normalizeModel(query.model)
  if (normalized) model.value = normalized
  if (isEngine(query.engine)) engine.value = query.engine
  if (isTarget(query.target)) target.value = query.target
}

initFromQuery()

const resolved = computed(() => resolveModule(model.value, engine.value, target.value))
const schemaMeta = computed(() => {
  if (!resolved.value) return undefined
  const meta = SCHEMA_META[resolved.value.schemaName]
  return { title: t(meta.titleKey), area: t(meta.areaKey) }
})

watch([model, engine, target], () => {
  if (!isEngineSupported(model.value, engine.value)) {
    engine.value = firstSupportedEngine(model.value) ?? engine.value
  }
  if (!isTargetSupported(model.value, engine.value, target.value)) {
    target.value = firstSupportedTarget(model.value, engine.value) ?? target.value
  }
  router.replace({ query: { model: model.value, engine: engine.value, target: target.value } })
})

function callChild(method: keyof TrainingChildActions) {
  childRef.value?.[method]?.()
}
</script>

<template>
  <div class="workbench-page">
    <div v-if="!resolved" class="workbench-fallback">
      <WorkbenchHeader @save="callChild('saveConfig')" @import="callChild('openImport')" @reset="callChild('resetConfig')" />
      <TrainingSelector v-model:model="model" v-model:engine="engine" v-model:target="target" />
      <div class="unsupported-hint"><strong>{{ t("training.selector.unsupported") }}</strong></div>
    </div>
    <AnimaFastPage v-else-if="resolved.schemaName === 'anima-lora-fast'" ref="childRef" bare>
      <template #form-top>
        <WorkbenchHeader @save="callChild('saveConfig')" @import="callChild('openImport')" @reset="callChild('resetConfig')" />
        <TrainingSelector v-model:model="model" v-model:engine="engine" v-model:target="target" />
      </template>
    </AnimaFastPage>
    <TrainingPage v-else-if="schemaMeta" :key="resolved.storageKey || resolved.schemaName" ref="childRef" bare :title="schemaMeta.title" :area="schemaMeta.area" :schema-name="resolved.schemaName" :field-defaults="resolved.defaults" :storage-key="resolved.storageKey" :legacy-storage-key="resolved.legacyStorageKey">
      <template #form-top>
        <WorkbenchHeader @save="callChild('saveConfig')" @import="callChild('openImport')" @reset="callChild('resetConfig')" />
        <TrainingSelector v-model:model="model" v-model:engine="engine" v-model:target="target" />
      </template>
    </TrainingPage>
  </div>
</template>

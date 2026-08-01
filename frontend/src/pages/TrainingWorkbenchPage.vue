<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { useI18n } from "vue-i18n"
import AnimaFastPage from "./AnimaFastPage.vue"
import TrainingPage from "./TrainingPage.vue"
import {
  DEFAULT_SELECTION,
  SCHEMA_META,
  TRAINING_ENGINES,
  TRAINING_MODELS,
  TRAINING_TARGETS,
  firstSupportedEngine,
  firstSupportedTarget,
  isEngineSupported,
  isTargetSupported,
  moduleForSchema,
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

function isModel(value: unknown): value is TrainingModel { return TRAINING_MODELS.includes(value as TrainingModel) }
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
  if (isModel(query.model)) model.value = query.model
  if (isEngine(query.engine)) engine.value = query.engine
  if (isTarget(query.target)) target.value = query.target
}

initFromQuery()

const resolved = computed(() => resolveModule(model.value, engine.value, target.value))
const schemaMeta = computed(() => resolved.value ? SCHEMA_META[resolved.value.schemaName] : undefined)

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
    <header class="workbench-header">
      <div><h1>{{ t("training.title") }}</h1><p>{{ t("training.subtitle") }}</p></div>
      <div class="workbench-actions">
        <button class="ghost-button" @click="callChild('saveConfig')">{{ t("training.actions.save") }}</button>
        <button class="ghost-button" @click="callChild('openImport')">{{ t("training.actions.import") }}</button>
        <button class="ghost-button" @click="callChild('resetConfig')">{{ t("training.actions.reset") }}</button>
      </div>
    </header>

    <section class="workbench-selector">
      <div class="selector-card">
        <h2>{{ t("training.selector.group") }}</h2>
        <div class="selector-grid">
          <label>{{ t("training.selector.model") }}
            <select v-model="model">
              <option v-for="item in TRAINING_MODELS" :key="item" :value="item">{{ t(`training.selector.models.${item}`) }}</option>
            </select>
          </label>
          <label>{{ t("training.selector.engine") }}
            <select v-model="engine">
              <option v-for="item in TRAINING_ENGINES" :key="item" :value="item" :disabled="!isEngineSupported(model, item)">{{ t(`training.selector.engines.${item}`) }}</option>
            </select>
          </label>
        </div>
      </div>
      <div class="selector-card">
        <h2>{{ t("training.selector.target") }}</h2>
        <div class="segmented" role="group" :aria-label="t('training.selector.targetType')">
          <button v-for="item in TRAINING_TARGETS" :key="item" :class="{ active: target === item }" :disabled="!isTargetSupported(model, engine, item)" @click="target = item">{{ t(`training.selector.targets.${item}`) }}</button>
        </div>
      </div>
    </section>

    <div v-if="!resolved" class="unsupported-hint"><strong>{{ t("training.selector.unsupported") }}</strong></div>
    <AnimaFastPage v-else-if="resolved.schemaName === 'anima-lora-fast'" ref="childRef" bare />
    <TrainingPage v-else-if="schemaMeta" :key="resolved.schemaName" ref="childRef" bare :title="schemaMeta.title" :area="schemaMeta.area" :schema-name="resolved.schemaName" />
  </div>
</template>

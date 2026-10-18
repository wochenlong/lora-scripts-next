<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { ElMessage } from "element-plus"
import { useI18n } from "vue-i18n"
import AnimaFastPage from "./AnimaFastPage.vue"
import DiffSynthGatePage from "./DiffSynthGatePage.vue"
import MossGatePage from "./MossGatePage.vue"
import KohakuMossPage from "./KohakuMossPage.vue"
import KohyaGatePage from "./KohyaGatePage.vue"
import MusubiGatePage from "./MusubiGatePage.vue"
import AiToolkitGatePage from "./AiToolkitGatePage.vue"
import TrainingPage from "./TrainingPage.vue"
import TrainingSelector from "../components/TrainingSelector.vue"
import WorkbenchHeader from "../components/WorkbenchHeader.vue"
import { enginesApi } from "../api/engines"
import { lastSelectionFor, rememberSelection } from "../engines/prefs"
import type { EngineRuntimeState } from "../engines/catalog"
import {
  DEFAULT_SELECTION,
  SCHEMA_META,
  TRAINING_ENGINES,
  TRAINING_TARGETS,
  firstSupportedTarget,
  idealEngineFor,
  isEngineReadyForAutoSelect,
  isEngineSupported,
  isTargetSupported,
  moduleForSchema,
  normalizeModel,
  recommendedEngineFor,
  resolveModule,
  type TrainingEngine,
  type TrainingModel,
  type TrainingTarget,
} from "../training/modules"

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const model = ref<TrainingModel>(DEFAULT_SELECTION.model)
const engine = ref<TrainingEngine>(DEFAULT_SELECTION.engine)
const target = ref<TrainingTarget>(DEFAULT_SELECTION.target)
/** True when the user (or an explicit URL) chose the engine; blocks install-aware auto-switch. */
const enginePinned = ref(false)
const engineStates = ref<Partial<Record<TrainingEngine, EngineRuntimeState>>>({})
const readinessKnown = ref(false)

function isEngine(value: unknown): value is TrainingEngine { return TRAINING_ENGINES.includes(value as TrainingEngine) }
function isTarget(value: unknown): value is TrainingTarget { return TRAINING_TARGETS.includes(value as TrainingTarget) }

function isAvailable(engineId: TrainingEngine): boolean {
  if (!readinessKnown.value) return false
  return isEngineReadyForAutoSelect(engineStates.value[engineId])
}

/** Engine for a model: remembered ready choice, else readiness-aware recommendation. */
function engineForModel(next: TrainingModel): TrainingEngine {
  const remembered = lastSelectionFor(next)
  if (remembered && isEngine(remembered.engine) && isEngineSupported(next, remembered.engine)) {
    if (readinessKnown.value) {
      if (isAvailable(remembered.engine)) return remembered.engine
    } else if (!(next === "anima" && remembered.engine === "anima-fast")) {
      // Cold start: never open Anima Fast from memory before install state is known.
      return remembered.engine
    }
  }
  return recommendedEngineFor(next, readinessKnown.value ? isAvailable : undefined) ?? DEFAULT_SELECTION.engine
}

function targetForModel(next: TrainingModel, nextEngine: TrainingEngine): TrainingTarget {
  const remembered = lastSelectionFor(next)
  if (remembered && isTarget(remembered.target) && isTargetSupported(next, nextEngine, remembered.target)) {
    return remembered.target
  }
  return firstSupportedTarget(next, nextEngine) ?? DEFAULT_SELECTION.target
}

function applyAutoEngine(next: TrainingModel = model.value) {
  if (enginePinned.value) return
  const nextEngine = engineForModel(next)
  if (nextEngine !== engine.value) engine.value = nextEngine
  const nextTarget = targetForModel(next, engine.value)
  if (nextTarget !== target.value) target.value = nextTarget
}

function initFromQuery() {
  const query = route.query
  const fromSchema = typeof query.schema === "string" ? moduleForSchema(query.schema) : undefined
  if (fromSchema) {
    model.value = fromSchema.model
    engine.value = fromSchema.engine
    target.value = fromSchema.target
    enginePinned.value = true
    return
  }
  const normalized = normalizeModel(query.model)
  if (normalized) model.value = normalized
  if (isEngine(query.engine)) {
    engine.value = query.engine
    enginePinned.value = true
  } else {
    engine.value = engineForModel(model.value)
  }
  target.value = isTarget(query.target) ? query.target : targetForModel(model.value, engine.value)
}

initFromQuery()

onMounted(async () => {
  try {
    const statuses = await enginesApi.list()
    const next: Partial<Record<TrainingEngine, EngineRuntimeState>> = {}
    for (const status of statuses) next[status.id] = status.state
    engineStates.value = next
    readinessKnown.value = true
    // Re-resolve after install state is known: Anima upgrades to Fast when ready,
    // or stays/falls back to Kohya when Fast is not installed.
    applyAutoEngine()
  } catch {
    // Keep cold-start recommendation when status cannot be loaded.
  }
})

const resolved = computed(() => resolveModule(model.value, engine.value, target.value))
const schemaMeta = computed(() => {
  if (!resolved.value) return undefined
  const meta = SCHEMA_META[resolved.value.schemaName]
  return { title: t(meta.titleKey), area: t(meta.areaKey) }
})

function onEnginePickedByUser() {
  enginePinned.value = true
}

watch(model, (next, prev) => {
  if (next === prev) return
  // Model changes clear a prior pin so the new model gets its own recommendation.
  enginePinned.value = false
  applyAutoEngine(next)
})

watch([model, engine, target], () => {
  let adjusted = false
  if (!isEngineSupported(model.value, engine.value)) {
    enginePinned.value = false
    engine.value = recommendedEngineFor(model.value, readinessKnown.value ? isAvailable : undefined) ?? engine.value
    adjusted = true
  }
  if (!isTargetSupported(model.value, engine.value, target.value)) {
    target.value = firstSupportedTarget(model.value, engine.value) ?? target.value
    adjusted = true
  }
  if (adjusted) ElMessage.info(t("training.selector.autoAdjusted"))
  // Auto fallback (e.g. Anima→Kohya while Fast is missing) remembers the ideal
  // engine, so Fast becomes the default again once it is installed.
  const engineToRemember = enginePinned.value
    ? engine.value
    : (idealEngineFor(model.value) ?? engine.value)
  void rememberSelection(model.value, engineToRemember, target.value).catch((error: unknown) => {
    ElMessage.error(error instanceof Error ? error.message : t("engineSettings.saveFailed"))
  })
  // Only persist engine in the URL when the user explicitly pinned it.
  // Auto-selected engines must not pin on reload, or Fast can never replace a
  // Kohya fallback after install.
  router.replace({
    query: {
      model: model.value,
      ...(enginePinned.value ? { engine: engine.value } : {}),
      target: target.value,
    },
  })
})
</script>

<template>
  <div class="workbench-page">
    <div v-if="!resolved" class="workbench-fallback">
      <WorkbenchHeader />
      <TrainingSelector v-model:model="model" v-model:engine="engine" v-model:target="target" @engine-picked="onEnginePickedByUser" />
      <div class="unsupported-hint"><strong>{{ t("training.selector.unsupported") }}</strong></div>
    </div>
    <AnimaFastPage v-else-if="resolved.schemaName === 'anima-lora-fast'" bare>
      <template #form-top>
        <WorkbenchHeader />
        <TrainingSelector v-model:model="model" v-model:engine="engine" v-model:target="target" @engine-picked="onEnginePickedByUser" />
      </template>
    </AnimaFastPage>
    <MossGatePage v-else-if="resolved.engine === 'moss'" bare>
      <template #form-top>
        <WorkbenchHeader />
        <TrainingSelector v-model:model="model" v-model:engine="engine" v-model:target="target" @engine-picked="onEnginePickedByUser" />
      </template>
    </MossGatePage>
    <KohakuMossPage v-else-if="resolved.engine === 'kohaku-moss'" bare>
      <template #form-top>
        <WorkbenchHeader />
        <TrainingSelector v-model:model="model" v-model:engine="engine" v-model:target="target" @engine-picked="onEnginePickedByUser" />
      </template>
    </KohakuMossPage>
    <DiffSynthGatePage v-else-if="resolved.engine === 'diffsynth'" bare>
      <template #form-top>
        <WorkbenchHeader />
        <TrainingSelector v-model:model="model" v-model:engine="engine" v-model:target="target" @engine-picked="onEnginePickedByUser" />
      </template>
    </DiffSynthGatePage>
    <MusubiGatePage v-else-if="resolved.engine === 'musubi'" :schema-name="resolved.schemaName" bare>
      <template #form-top>
        <WorkbenchHeader />
        <TrainingSelector v-model:model="model" v-model:engine="engine" v-model:target="target" @engine-picked="onEnginePickedByUser" />
      </template>
    </MusubiGatePage>
    <AiToolkitGatePage v-else-if="resolved.engine === 'ai-toolkit'" :schema-name="resolved.schemaName" bare>
      <template #form-top>
        <WorkbenchHeader />
        <TrainingSelector v-model:model="model" v-model:engine="engine" v-model:target="target" @engine-picked="onEnginePickedByUser" />
      </template>
    </AiToolkitGatePage>
    <KohyaGatePage v-else-if="resolved.engine === 'kohya' && schemaMeta" :key="resolved.storageKey || resolved.schemaName" bare :title="schemaMeta.title" :area="schemaMeta.area" :schema-name="resolved.schemaName" :field-defaults="resolved.defaults" :storage-key="resolved.storageKey" :legacy-storage-key="resolved.legacyStorageKey">
      <template #form-top>
        <WorkbenchHeader />
        <TrainingSelector v-model:model="model" v-model:engine="engine" v-model:target="target" @engine-picked="onEnginePickedByUser" />
      </template>
    </KohyaGatePage>
    <TrainingPage v-else-if="schemaMeta" :key="resolved.storageKey || resolved.schemaName" bare :title="schemaMeta.title" :area="schemaMeta.area" :schema-name="resolved.schemaName" :field-defaults="resolved.defaults" :storage-key="resolved.storageKey" :legacy-storage-key="resolved.legacyStorageKey">
      <template #form-top>
        <WorkbenchHeader />
        <TrainingSelector v-model:model="model" v-model:engine="engine" v-model:target="target" @engine-picked="onEnginePickedByUser" />
      </template>
    </TrainingPage>
  </div>
</template>

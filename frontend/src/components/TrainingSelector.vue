<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { useI18n } from "vue-i18n"
import { enginesApi } from "../api/engines"
import type { EngineRuntimeState } from "../engines/catalog"
import {
  MODEL_PICKER_ORDER,
  TRAINING_ENGINES,
  TRAINING_SCENARIOS,
  TRAINING_TARGETS,
  enginePreferenceOrder,
  idealEngineFor,
  isEngineReadyForAutoSelect,
  isEngineSupported,
  isTargetSupported,
  modelForScenario,
  recommendedEngineFor,
  type TrainingEngine,
  type TrainingModel,
  type TrainingScenario,
  type TrainingTarget,
} from "../training/modules"

const model = defineModel<TrainingModel>("model", { required: true })
const engine = defineModel<TrainingEngine>("engine", { required: true })
const target = defineModel<TrainingTarget>("target", { required: true })
const emit = defineEmits<{ enginePicked: [] }>()
const { t } = useI18n()

const guideOpen = ref(false)
const engineStates = ref<Partial<Record<TrainingEngine, EngineRuntimeState>>>({})
const readinessKnown = ref(false)

const idealEngine = computed(() => idealEngineFor(model.value))
const recommendedEngine = computed(() => recommendedEngineFor(
  model.value,
  readinessKnown.value ? (id) => isEngineReadyForAutoSelect(engineStates.value[id]) : undefined,
))
const usingRecommended = computed(() => engine.value === recommendedEngine.value)
const unsupportedTargets = computed(() => TRAINING_TARGETS.filter((item) => !isTargetSupported(model.value, engine.value, item)))

const supportedEngines = computed(() => {
  const preferred = enginePreferenceOrder(model.value)
  const rest = TRAINING_ENGINES.filter((item) => isEngineSupported(model.value, item) && !preferred.includes(item))
  return [...preferred, ...rest]
})
const hiddenEngineCount = computed(() => TRAINING_ENGINES.length - supportedEngines.value.length)
const showEngineHint = computed(() => currentEngineMissing.value || hiddenEngineCount.value > 0 || !usingRecommended.value)

function isInstallReady(engineId: TrainingEngine): boolean {
  const state = engineStates.value[engineId]
  return state === "ready" || state === "installed_unverified"
}

/** Only engines that can train the current model. Ready ones lead. */
const enginePickerOrder = computed(() => {
  const supported = supportedEngines.value
  return [
    ...supported.filter((item) => isInstallReady(item)),
    ...supported.filter((item) => !isInstallReady(item)),
  ]
})

type EngineDotStatus = "ready" | "needs-install"

function engineDotStatus(engineId: TrainingEngine): EngineDotStatus {
  return isInstallReady(engineId) ? "ready" : "needs-install"
}

function engineStatusText(engineId: TrainingEngine): string {
  const state = engineStates.value[engineId] ?? "unknown"
  if (state === "not_installed") return t("training.selector.engineNeedsDownload")
  if (state === "broken") return t("training.selector.engineStates.broken")
  if (state === "installing" || state === "auditing") return t("training.selector.engineStates.installing")
  if (state === "ready") return t("training.selector.engineStates.ready")
  if (state === "installed_unverified") return t("training.selector.engineStates.installedUnverified")
  return t("training.selector.engineStates.unknown")
}

function engineClosedLabel(engineId: TrainingEngine): string {
  const name = t(`training.selector.engines.${engineId}`)
  const recommended = engineId === idealEngine.value ? ` · ${t("training.selector.engineRecommended")}` : ""
  return `${name}${recommended}`
}

function applyScenarioTip(scenario: TrainingScenario) {
  model.value = modelForScenario(scenario)
  guideOpen.value = false
}

function modelOptionLabel(item: TrainingModel): string {
  const name = t(`training.selector.models.${item}`)
  const tag = t(`training.selector.modelTags.${item}`)
  return tag ? `${name} — ${tag}` : name
}

onMounted(async () => {
  try {
    const statuses = await enginesApi.list()
    const next: Partial<Record<TrainingEngine, EngineRuntimeState>> = {}
    for (const status of statuses) next[status.id] = status.state
    engineStates.value = next
    readinessKnown.value = true
  } catch {
    // Install state is advisory here: fall back to plain engine names.
  }
})

function onEngineSelect() {
  emit("enginePicked")
}

const currentEngineMissing = computed(() => {
  const state = engineStates.value[engine.value]
  return state === "not_installed" || state === "broken"
})

const engineHintText = computed(() => {
  if (currentEngineMissing.value) {
    return t("training.selector.engineMissing", { list: t(`training.selector.engines.${engine.value}`) })
  }
  if (hiddenEngineCount.value > 0) {
    return t("training.selector.engineUnsupportedHidden", { n: hiddenEngineCount.value })
  }
  if (!usingRecommended.value) {
    return t("training.selector.engineManualHint")
  }
  return ""
})

</script>

<template>
  <div class="workbench-selector">
    <div class="selector-card">
      <h2>{{ t("training.selector.group") }}</h2>
      <div class="selector-grid selector-grid-parallel">
        <div class="selector-model">
          <label class="selector-model-field">
            {{ t("training.selector.model") }}
            <ElSelect
              v-model="model"
              class="selector-model-select"
              data-testid="model-select"
              :aria-label="t('training.selector.model')"
              :teleported="true"
              fit-input-width
            >
              <ElOption
                v-for="item in MODEL_PICKER_ORDER"
                :key="item"
                :value="item"
                :label="modelOptionLabel(item)"
              >
                <span class="model-option">
                  <span class="model-option-name">{{ t(`training.selector.models.${item}`) }}</span>
                  <span v-if="t(`training.selector.modelTags.${item}`)" class="model-option-tag">{{ t(`training.selector.modelTags.${item}`) }}</span>
                </span>
              </ElOption>
            </ElSelect>
          </label>
          <p class="selector-model-hint" data-testid="model-use-hint">{{ t(`training.selector.modelHints.${model}`) }}</p>
        </div>
        <div class="selector-engine" data-testid="engine-auto">
          <label class="selector-engine-field">
            {{ t("training.selector.engine") }}
            <ElSelect
              v-model="engine"
              class="selector-engine-select"
              data-testid="engine-select"
              :aria-label="t('training.selector.engine')"
              :teleported="true"
              fit-input-width
              @change="onEngineSelect"
            >
              <ElOption
                v-for="item in enginePickerOrder"
                :key="item"
                :value="item"
                :label="engineClosedLabel(item)"
              >
                <span class="engine-option" :data-status="engineDotStatus(item)">
                  <i class="engine-dot" :data-status="engineDotStatus(item)" aria-hidden="true" />
                  <span class="engine-option-name">{{ t(`training.selector.engines.${item}`) }}</span>
                  <span v-if="item === idealEngine" class="engine-option-tag">{{ t("training.selector.engineRecommended") }}</span>
                  <span class="engine-option-status">{{ engineStatusText(item) }}</span>
                </span>
              </ElOption>
            </ElSelect>
          </label>
          <p class="selector-engine-legend" data-testid="engine-legend">
            <span><i class="engine-dot" data-status="ready" aria-hidden="true" />{{ t("training.selector.engineLegendReady") }}</span>
            <span><i class="engine-dot" data-status="needs-install" aria-hidden="true" />{{ t("training.selector.engineLegendNeedsInstall") }}</span>
          </p>
          <p v-if="showEngineHint" class="selector-engine-hint" data-testid="engine-hint">{{ engineHintText }}</p>
        </div>
        <div class="selector-guide" data-testid="model-guide">
          <button
            type="button"
            class="selector-guide-toggle"
            data-testid="model-guide-toggle"
            :aria-expanded="guideOpen"
            @click="guideOpen = !guideOpen"
          >{{ guideOpen ? t("training.selector.guideHide") : t("training.selector.guideLabel") }}</button>
          <div v-if="guideOpen" class="selector-guide-panel" data-testid="model-guide-panel">
            <button
              v-for="item in TRAINING_SCENARIOS"
              :key="item.id"
              type="button"
              class="selector-guide-link"
              @click="applyScenarioTip(item.id)"
            >
              <span>{{ t(`training.selector.scenarios.${item.id}`) }}</span>
              <span class="selector-guide-arrow">→</span>
              <span>{{ t(`training.selector.models.${item.model}`) }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
    <div class="selector-card">
      <h2>{{ t("training.selector.target") }}</h2>
      <div class="segmented" role="group" :aria-label="t('training.selector.targetType')">
        <button v-for="item in TRAINING_TARGETS" :key="item" :class="{ active: target === item }" :disabled="!isTargetSupported(model, engine, item)" @click="target = item">{{ t(`training.selector.targets.${item}`) }}</button>
      </div>
      <p v-if="unsupportedTargets.length" class="selector-hint">{{ t("training.selector.unsupportedForModel", { list: unsupportedTargets.map((item) => t(`training.selector.targets.${item}`)).join(" / ") }) }}</p>
    </div>
  </div>
</template>

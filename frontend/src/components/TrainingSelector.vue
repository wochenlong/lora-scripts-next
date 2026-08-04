<script setup lang="ts">
import { computed } from "vue"
import { useI18n } from "vue-i18n"
import {
  TRAINING_ENGINES,
  TRAINING_MODELS,
  TRAINING_TARGETS,
  isEngineSupported,
  isTargetSupported,
  type TrainingEngine,
  type TrainingModel,
  type TrainingTarget,
} from "../training/modules"

const model = defineModel<TrainingModel>("model", { required: true })
const engine = defineModel<TrainingEngine>("engine", { required: true })
const target = defineModel<TrainingTarget>("target", { required: true })
const { t } = useI18n()

const unsupportedEngines = computed(() => TRAINING_ENGINES.filter((item) => !isEngineSupported(model.value, item)))
const unsupportedTargets = computed(() => TRAINING_TARGETS.filter((item) => !isTargetSupported(model.value, engine.value, item)))
</script>

<template>
  <div class="workbench-selector">
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
        <p v-if="unsupportedEngines.length" class="selector-hint">{{ t("training.selector.unsupportedForModel", { list: unsupportedEngines.map((item) => t(`training.selector.engines.${item}`)).join(" / ") }) }}</p>
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

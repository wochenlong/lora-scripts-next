<script setup lang="ts">
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
      </div>
    </div>
    <div class="selector-card">
      <h2>{{ t("training.selector.target") }}</h2>
      <div class="segmented" role="group" :aria-label="t('training.selector.targetType')">
        <button v-for="item in TRAINING_TARGETS" :key="item" :class="{ active: target === item }" :disabled="!isTargetSupported(model, engine, item)" @click="target = item">{{ t(`training.selector.targets.${item}`) }}</button>
      </div>
    </div>
  </div>
</template>

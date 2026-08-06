<script setup lang="ts">
import { computed } from "vue"
import { useI18n } from "vue-i18n"
import { RouterLink } from "vue-router"
import type { EngineRuntimeState } from "../engines/catalog"

const props = withDefaults(defineProps<{
  state: EngineRuntimeState
  title?: string
  hint?: string
  loading?: boolean
  showInstall?: boolean
  showReinstall?: boolean
  showRefresh?: boolean
  /** When true, only show the manage link (typical for ready training form). */
  manageOnly?: boolean
  manageTo?: string
}>(), {
  showRefresh: false,
  manageOnly: false,
  manageTo: "/settings/engines",
})

const emit = defineEmits<{
  refresh: []
  install: []
  reinstall: []
}>()

const { t } = useI18n()

const label = computed(() => {
  if (props.title) return props.title
  const key = `settings.engines.state.${props.state}`
  const translated = t(key)
  return translated === key ? props.state : translated
})

const resolvedHint = computed(() => {
  if (props.hint) return props.hint
  const key = `settings.engines.hint.${props.state}`
  const translated = t(key)
  return translated === key ? "" : translated
})
</script>

<template>
  <div class="engine-status-bar" :data-state="state" data-testid="engine-status-bar">
    <div class="engine-status-copy">
      <b>{{ label }}</b>
      <span v-if="resolvedHint">{{ resolvedHint }}</span>
    </div>
    <div class="engine-status-actions">
      <template v-if="!manageOnly">
        <button v-if="showRefresh" type="button" class="ghost-button" :disabled="loading" @click="emit('refresh')">
          {{ t("settings.engines.actions.refresh") }}
        </button>
        <button v-if="showInstall" type="button" class="ghost-button" :disabled="loading" @click="emit('install')">
          {{ t("settings.engines.actions.install") }}
        </button>
        <button v-if="showReinstall" type="button" class="ghost-button" :disabled="loading" @click="emit('reinstall')">
          {{ t("settings.engines.actions.reinstall") }}
        </button>
      </template>
      <RouterLink class="ghost-button" :to="manageTo">{{ t("settings.engines.actions.manage") }}</RouterLink>
    </div>
  </div>
</template>

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
  showRepair?: boolean
  showReinstall?: boolean
  showRefresh?: boolean
  /** When true, only show the manage link (typical for ready training form). */
  manageOnly?: boolean
  /** Hide the manage link when a sibling CTA already offers it. */
  showManage?: boolean
  manageTo?: string
}>(), {
  title: "",
  hint: "",
  showRefresh: false,
  showRepair: false,
  manageOnly: false,
  showManage: true,
  manageTo: "/settings/engines",
})

const emit = defineEmits<{
  refresh: []
  install: []
  repair: []
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

const showActionRow = computed(() => {
  if (props.manageOnly) return props.showManage
  return Boolean(props.showRefresh || props.showInstall || props.showReinstall || props.showManage)
})
</script>

<template>
  <div class="engine-status-bar" :data-state="state" data-testid="engine-status-bar">
    <div class="engine-status-copy">
      <b>{{ label }}</b>
      <span v-if="resolvedHint">{{ resolvedHint }}</span>
    </div>
    <div v-if="showActionRow" class="engine-status-actions">
      <template v-if="!manageOnly">
        <button v-if="showRefresh" type="button" class="ghost-button" :disabled="loading" @click="emit('refresh')">
          {{ t("settings.engines.actions.refresh") }}
        </button>
        <button v-if="showInstall" type="button" class="ghost-button" :disabled="loading" @click="emit('install')">
          {{ t("settings.engines.actions.install") }}
        </button>
        <button v-if="showRepair" type="button" class="ghost-button" :disabled="loading" @click="emit('repair')">
          {{ t("settings.engines.actions.repair") }}
        </button>
        <button v-if="showReinstall" type="button" class="ghost-button" :disabled="loading" @click="emit('reinstall')">
          {{ t("settings.engines.actions.reinstall") }}
        </button>
      </template>
      <RouterLink v-if="showManage" class="ghost-button" :to="manageTo">{{ t("settings.engines.actions.manage") }}</RouterLink>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from "vue"
import { CircleCheck, CloseBold } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import type { PluginConfirmationDecision, PluginConfirmationProjection } from "../../api/plugins"

const props = defineProps<{
  confirmation: PluginConfirmationProjection
  pluginName: string
  busy?: boolean
  error?: string
}>()
const emit = defineEmits<{ resolve: [decision: PluginConfirmationDecision] }>()
const { t } = useI18n()
const layer = ref<HTMLElement | null>(null)
const rejectButton = ref<HTMLButtonElement | null>(null)
const expired = computed(
  () =>
    !["pending", "presented"].includes(props.confirmation.state) ||
    Date.parse(props.confirmation.expiresAt) <= Date.now(),
)
const detailRows = computed(() =>
  Object.entries(props.confirmation.details).map(([key, value]) => ({
    key,
    value: typeof value === "string" ? value : JSON.stringify(value),
  })),
)

function resolve(decision: PluginConfirmationDecision) {
  if (!props.busy && !expired.value) emit("resolve", decision)
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") {
    event.preventDefault()
    resolve("rejected")
    return
  }
  if (event.key !== "Tab" || !layer.value) return
  const controls = [...layer.value.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")]
  if (controls.length === 0) return
  const current = controls.indexOf(document.activeElement as HTMLButtonElement)
  const next = event.shiftKey ? (current <= 0 ? controls.length - 1 : current - 1) : (current + 1) % controls.length
  event.preventDefault()
  controls[next].focus()
}

onMounted(() => void nextTick(() => rejectButton.value?.focus()))
</script>

<template>
  <div
    ref="layer"
    class="host-confirmation-layer"
    role="dialog"
    aria-modal="true"
    :aria-labelledby="`host-confirmation-title-${confirmation.ticketId}`"
    :aria-describedby="`host-confirmation-summary-${confirmation.ticketId}`"
    data-testid="host-confirmation-layer"
    @keydown="onKeydown"
  >
    <section class="host-confirmation-dialog">
      <header>
        <span class="host-confirmation-brand">{{ t("extensionHost.confirmation.host") }}</span>
        <small>{{ pluginName }}</small>
        <h2 :id="`host-confirmation-title-${confirmation.ticketId}`">{{ confirmation.title }}</h2>
      </header>
      <dl>
        <div>
          <dt>{{ t("extensionHost.confirmation.action") }}</dt>
          <dd>{{ confirmation.action }}</dd>
        </div>
        <div>
          <dt>{{ t("extensionHost.confirmation.permission") }}</dt>
          <dd>{{ confirmation.permission }}</dd>
        </div>
        <div v-if="confirmation.artifactIds?.length">
          <dt>{{ t("extensionHost.confirmation.artifacts") }}</dt>
          <dd>{{ confirmation.artifactIds.join(", ") }}</dd>
        </div>
        <div v-for="detail in detailRows" :key="detail.key">
          <dt>{{ detail.key }}</dt>
          <dd>{{ detail.value }}</dd>
        </div>
      </dl>
      <p :id="`host-confirmation-summary-${confirmation.ticketId}`">{{ confirmation.summary }}</p>
      <p v-if="expired" class="host-confirmation-error" role="alert">{{ t("extensionHost.confirmation.expired") }}</p>
      <p v-else-if="error" class="host-confirmation-error" role="alert">{{ error }}</p>
      <footer>
        <button ref="rejectButton" type="button" class="secondary-action" :disabled="busy || expired" @click="resolve('rejected')">
          <CloseBold aria-hidden="true" />
          {{ t("extensionHost.confirmation.reject") }}
        </button>
        <button type="button" class="primary-action" :disabled="busy || expired" @click="resolve('approved')">
          <CircleCheck aria-hidden="true" />
          {{ busy ? t("extensionHost.confirmation.resolving") : t("extensionHost.confirmation.approve") }}
        </button>
      </footer>
    </section>
  </div>
</template>

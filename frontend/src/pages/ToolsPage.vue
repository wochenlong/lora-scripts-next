<script setup lang="ts">
import { reactive, ref } from "vue"
import { ElMessage } from "element-plus"
import { useI18n } from "vue-i18n"
import { AVAILABLE_SCRIPTS, toolsApi, type ToolScript } from "../api/tools"

const { t } = useI18n()
const script = ref<ToolScript>(AVAILABLE_SCRIPTS[0])
const rows = reactive([{ key: "", value: "" }])
const submitting = ref(false)
function addRow() { rows.push({ key: "", value: "" }) }
function removeRow(index: number) { rows.splice(index, 1); if (!rows.length) addRow() }
function parseValue(value: string): string | number | boolean {
  if (value === "true") return true
  if (value === "false") return false
  const number = Number(value)
  return value !== "" && Number.isFinite(number) ? number : value
}
async function run() {
  const args: Record<string, string | number | boolean> = {}
  for (const row of rows) {
    const key = row.key.trim().replace(/^--/, "")
    if (key) args[key] = parseValue(row.value.trim())
  }
  submitting.value = true
  try { await toolsApi.run(script.value, args); ElMessage.success(t("tools.msg.submitted")) }
  catch (error) { ElMessage.error(error instanceof Error ? error.message : t("tools.msg.submitFail")) }
  finally { submitting.value = false }
}
</script>

<template>
  <div class="simple-page"><header><span class="eyebrow">SCRIPT TOOLS</span><h1>{{ t("tools.title") }}</h1><p>{{ t("tools.subtitle") }}</p></header>
    <section class="settings-card"><label for="tool-script">{{ t("tools.scriptLabel") }}</label><select id="tool-script" v-model="script"><option v-for="name in AVAILABLE_SCRIPTS" :key="name" :value="name">{{ name }}</option></select>
      <div class="argument-heading"><strong>{{ t("tools.argsTitle") }}</strong><button @click="addRow">{{ t("tools.addArg") }}</button></div>
      <div v-for="(row, index) in rows" :key="index" class="argument-row"><input v-model="row.key" :placeholder="t('tools.argKeyPlaceholder')" /><input v-model="row.value" :placeholder="t('tools.argValuePlaceholder')" /><button :aria-label="t('tools.removeArgAria')" @click="removeRow(index)">×</button></div>
      <div class="form-actions"><button class="primary-action" :disabled="submitting" @click="run">{{ submitting ? t("tools.submitting") : t("tools.run") }}</button></div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue"
import { useI18n } from "vue-i18n"
import type { TaggerModel } from "../api/tagger"
const props = defineProps<{ models: TaggerModel[]; selected: string; disabled: boolean }>()
const emit = defineEmits<{ select: [id: string] }>()
const { t } = useI18n()
const search = ref("")
const open = ref(false)
const current = computed(() => props.models.find(model => model.id === props.selected))
const families = computed(() => [...new Set(props.models.map(model => model.family))])
function matching(family: string) {
  const term = search.value.trim().toLowerCase()
  return props.models.filter(model => model.family === family && (!term || `${model.id} ${model.name} ${model.model}`.toLowerCase().includes(term)))
}
function choose(id: string) { emit("select", id); open.value = false; search.value = "" }
</script>

<template>
  <details :open="open" class="tagger-model-selector wide-field" @toggle="open = ($event.target as HTMLDetailsElement).open">
    <summary>{{ t('tagger.modelLabel') }}: {{ current?.model || t('tagger.models.loading') }} <span v-if="current?.downloaded">· {{ t('tagger.models.downloaded') }}</span></summary>
    <label>{{ t('tagger.models.search') }}<input v-model="search" type="search" :disabled="disabled" /></label>
    <template v-for="family in families" :key="family">
      <details v-if="matching(family).length" :open="!!search.trim() || current?.family === family" class="tagger-model-family">
        <summary>{{ family }}</summary>
        <button v-for="model in matching(family)" :key="model.id" type="button" :data-model-id="model.id" :class="{ active: selected === model.id }" :disabled="disabled" @click="choose(model.id)">
          <strong>{{ model.model }}</strong><small>{{ model.name }}<template v-if="model.author"> · {{ model.author }}</template> · {{ model.output === 'tag' ? t('tagger.modeTag') : t('tagger.modeNatural') }}<template v-if="model.downloaded"> · {{ t('tagger.models.downloaded') }}</template><template v-if="!model.ready"> · {{ t('tagger.models.notReady') }}</template></small>
        </button>
      </details>
    </template>
    <p v-if="!models.some(model => matching(model.family).length)">{{ t('tagger.models.noMatch') }}</p>
  </details>
</template>

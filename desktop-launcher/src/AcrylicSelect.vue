<script setup lang="ts" generic="T extends string | number = string | number">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useAttrs, useId, watch } from 'vue'
import { t } from './i18n'

defineOptions({ inheritAttrs: false })
interface Option { value: string | number; label: string; disabled?: boolean }
const props = defineProps<{ modelValue?: T; options: Option[]; disabled?: boolean; modelModifiers?: { number?: boolean }; placeholder?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: T]; change: [event: { target: { value: string } }] }>()
const attrs = useAttrs(), id = useId(), trigger = ref<HTMLButtonElement>(), popup = ref<HTMLElement>()
const opened = ref(false), active = ref(-1), reducedMotion = ref(false)
const associatedLabel = ref('')
const accessibleLabel = computed(() => typeof attrs['aria-label'] === 'string' ? attrs['aria-label'] : associatedLabel.value || undefined)
const position = ref<Record<string, string>>({}), selected = computed(() => props.options.findIndex(option => option.value === props.modelValue))
const label = computed(() => props.options[selected.value]?.label ?? props.placeholder ?? t('请选择'))
const activeId = computed(() => opened.value && active.value >= 0 ? `${id}-option-${active.value}` : undefined)
let typeAhead = '', typedAt = 0
let visibility: IntersectionObserver | undefined
let navigation: MutationObserver | undefined

function close() {
  opened.value = false
  document.removeEventListener('pointerdown', outside, true)
  document.removeEventListener('focusin', focusOutside, true)
  window.removeEventListener('resize', close)
  window.removeEventListener('scroll', scrolled, true)
  navigation?.disconnect()
}
function outside(event: PointerEvent) {
  if (!event.composedPath().includes(trigger.value!) && !event.composedPath().includes(popup.value!)) close()
}
function focusOutside(event: FocusEvent) {
  if (!trigger.value?.contains(event.target as Node) && !popup.value?.contains(event.target as Node)) close()
}
function scrolled(event: Event) {
  if (!popup.value?.contains(event.target as Node)) close()
}
function revealActive() {
  void nextTick(() => popup.value?.querySelector<HTMLElement>(`[data-index="${active.value}"]`)?.scrollIntoView({ block: 'nearest' }))
}
async function open() {
  if (props.disabled || !trigger.value || !props.options.some(option => !option.disabled)) return
  reducedMotion.value = Boolean(trigger.value.closest('.reduce-motion')) || matchMedia('(prefers-reduced-motion: reduce)').matches
  active.value = selected.value >= 0 && !props.options[selected.value]?.disabled ? selected.value : props.options.findIndex(option => !option.disabled)
  const rect = trigger.value.getBoundingClientRect()
  const width = Math.min(Math.max(rect.width, 160), innerWidth - 16)
  const below = innerHeight - rect.bottom - 8, above = rect.top - 8
  const upwards = below < Math.min(288, props.options.length * 36 + 8) && above > below
  const maxHeight = Math.max(36, Math.min(288, upwards ? above : below))
  position.value = { left: `${Math.max(8, Math.min(rect.left, innerWidth - width - 8))}px`, width: `${width}px`, maxHeight: `${maxHeight}px`, ...(upwards ? { bottom: `${innerHeight - rect.top + 4}px` } : { top: `${rect.bottom + 4}px` }) }
  opened.value = true
  document.addEventListener('pointerdown', outside, true)
  document.addEventListener('focusin', focusOutside, true)
  window.addEventListener('resize', close)
  window.addEventListener('scroll', scrolled, true)
  navigation = new MutationObserver(() => { if (!trigger.value?.getClientRects().length) close() })
  for (let ancestor = trigger.value.parentElement; ancestor; ancestor = ancestor.parentElement) navigation.observe(ancestor, { attributes: true, attributeFilter: ['style', 'class', 'data-page', 'data-setting'] })
  await nextTick()
  revealActive()
}
function choose(index: number) {
  const option = props.options[index]
  if (!option || option.disabled || props.disabled) return
  const changed = option.value !== props.modelValue
  close()
  if (changed) {
    emit('update:modelValue', option.value as T)
    emit('change', { target: { value: String(option.value) } })
  }
  trigger.value?.focus({ preventScroll: true })
}
function move(direction: number) {
  for (let i = active.value + direction; i >= 0 && i < props.options.length; i += direction) {
    if (!props.options[i]?.disabled) { active.value = i; revealActive(); return }
  }
}
function keydown(event: KeyboardEvent) {
  if (props.disabled) return
  if (event.key === 'Tab') { close(); return }
  if (event.key === 'Escape' || (event.altKey && event.key === 'ArrowUp')) { if (opened.value) { event.preventDefault(); event.stopPropagation(); close() }; return }
  if (['ArrowDown', 'ArrowUp', 'Home', 'End', 'Enter', ' '].includes(event.key)) {
    event.preventDefault()
    if (!opened.value) { void open(); return }
    if (event.key === 'Enter' || event.key === ' ') choose(active.value)
    else if (event.key === 'Home') { active.value = -1; move(1) }
    else if (event.key === 'End') { active.value = props.options.length; move(-1) }
    else move(event.key === 'ArrowDown' ? 1 : -1)
    return
  }
  if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
    event.preventDefault()
    const now = Date.now()
    typeAhead = now - typedAt > 700 ? event.key : typeAhead + event.key
    typedAt = now
    if (!opened.value) void open()
    const query = typeAhead.toLocaleLowerCase()
    const index = props.options.findIndex(option => !option.disabled && option.label.toLocaleLowerCase().startsWith(query))
    if (index >= 0) { active.value = index; revealActive() }
  }
}
watch(() => props.disabled, value => { if (value) close() })
watch(() => props.options.map(option => `${typeof option.value}:${option.value}:${Boolean(option.disabled)}`).join('\u0000'), () => {
  if (!opened.value) return
  if (!props.options.some(option => !option.disabled)) { close(); return }
  active.value = selected.value >= 0 && !props.options[selected.value]?.disabled ? selected.value : props.options.findIndex(option => !option.disabled)
  revealActive()
})
watch(() => props.modelValue, () => {
  if (opened.value && selected.value >= 0) { active.value = selected.value; revealActive() }
})
onMounted(() => {
  associatedLabel.value = Array.from(trigger.value?.labels ?? []).map(label => Array.from(label.childNodes).filter(node => node.nodeType === Node.TEXT_NODE).map(node => node.textContent?.trim()).filter(Boolean).join(' ')).filter(Boolean).join(' ')
  visibility = new IntersectionObserver(entries => { if (opened.value && entries.some(entry => !entry.isIntersecting)) close() })
  if (trigger.value) visibility.observe(trigger.value)
})
onBeforeUnmount(() => { close(); visibility?.disconnect() })
</script>

<template>
  <button ref="trigger" v-bind="attrs" type="button" class="acrylic-select" :class="{ 'is-open': opened }" role="combobox" aria-haspopup="listbox" :aria-label="accessibleLabel" :aria-expanded="opened" :aria-controls="opened ? `${id}-listbox` : undefined" :aria-activedescendant="activeId" :disabled="disabled" :title="typeof attrs.title === 'string' ? attrs.title : label" @click="opened ? close() : open()" @keydown="keydown">
    <span class="acrylic-select-label">{{ label }}</span><svg class="acrylic-select-chevron" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="m4 6 4 4 4-4" stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round" /></svg>
  </button>
  <Teleport to="body">
    <Transition :name="reducedMotion ? undefined : 'acrylic-flyout'">
      <div v-if="opened" :id="`${id}-listbox`" ref="popup" class="acrylic-select-popup" :class="{ 'reduce-motion': reducedMotion }" :style="position" role="listbox" :aria-label="accessibleLabel || t('选择选项')" @pointerdown.prevent>
        <div v-for="(option, index) in options" :id="`${id}-option-${index}`" :key="`${typeof option.value}:${option.value}`" :data-index="index" class="acrylic-select-option" :class="{ selected: option.value === modelValue, active: index === active, disabled: option.disabled }" role="option" :aria-selected="option.value === modelValue" :aria-disabled="Boolean(option.disabled)" @pointermove="!option.disabled && (active = index)" @click="choose(index)">{{ option.label }}</div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.acrylic-select{display:inline-flex;align-items:center;justify-content:space-between;gap:24px;min-width:120px;min-height:32px;max-width:100%;padding:6px 12px;border:1px solid #ffffff08;border-bottom-color:#ffffff0d;border-radius:4px;background:var(--control-bg,#ffffff0f);color:var(--fg,#fff);font:inherit;text-align:left;vertical-align:middle;cursor:default;transition:background 120ms,border-color 120ms;box-shadow:0 1px 1px #00000005}
.acrylic-select:hover:not(:disabled),.acrylic-select.is-open{background:var(--control-hover,#ffffff18)}
.acrylic-select:active:not(:disabled){background:#ffffff08;color:var(--fg-secondary,#d0d0d0);transform:none}
.acrylic-select:disabled{opacity:.4;cursor:default}
.acrylic-select-label{overflow:hidden;white-space:nowrap;text-overflow:ellipsis;min-width:0}
.acrylic-select-chevron{width:12px;height:12px;flex-shrink:0;transition:transform 160ms cubic-bezier(.1,.9,.2,1)}
.is-open .acrylic-select-chevron{transform:rotate(180deg)}
.acrylic-select-popup{position:fixed;z-index:10000;overflow:auto;overscroll-behavior:contain;padding:4px;border:1px solid #ffffff16;border-radius:6px;background:var(--flyout-bg,#282b2ce8);color:var(--fg,#fff);backdrop-filter:blur(40px) saturate(130%);box-shadow:0 8px 24px #0005,0 2px 5px #0003;font:14px/1.45 "Segoe UI Variable Text","Segoe UI","Microsoft YaHei UI",sans-serif;scrollbar-width:thin;scrollbar-color:var(--scrollbar,#ffffff44) transparent;transform-origin:top center}
@supports(backdrop-filter:url("#fluent-acrylic")){.acrylic-select-popup{background:#ffffff06;backdrop-filter:url("#fluent-acrylic")}}
.acrylic-select-option{position:relative;min-height:32px;padding:7px 10px 7px 12px;border-radius:3px;overflow-wrap:anywhere;cursor:default;user-select:none;transition:background 100ms}
.acrylic-select-option.active,.acrylic-select-option:hover:not(.disabled){background:var(--control-hover,#ffffff18)}
.acrylic-select-option.selected{background:var(--control-selected,#ffffff14)}
.acrylic-select-option.selected:before{content:"";position:absolute;left:0;top:8px;bottom:8px;width:3px;border-radius:2px;background:var(--accent,#91a5c3)}
.acrylic-select-option.disabled{opacity:.4}
.acrylic-flyout-enter-active{transition:opacity 250ms cubic-bezier(0,0,0,1),transform 250ms cubic-bezier(0,0,0,1)}
.acrylic-flyout-leave-active{transition:opacity 167ms cubic-bezier(0,0,0,1)}
.acrylic-flyout-enter-from{opacity:0;transform:translateY(-5px)}
.acrylic-flyout-leave-to{opacity:0}
:global(.reduce-motion) .acrylic-select-chevron{transition:none}
@media(prefers-reduced-motion:reduce){.acrylic-select,.acrylic-select-chevron,.acrylic-select-option,.acrylic-flyout-enter-active,.acrylic-flyout-leave-active{transition:none}}
</style>

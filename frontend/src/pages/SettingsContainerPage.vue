<script setup lang="ts">
import { computed, reactive, ref } from "vue"
import { ElMessage } from "element-plus"
import { useI18n } from "vue-i18n"
import { storeToRefs } from "pinia"
import AboutPage from "./AboutPage.vue"
import ChangelogPage from "./ChangelogPage.vue"
import { SUPPORTED_LOCALES, UI_CONFIGS_KEY, getStoredLocale, setLocale, type AppLocale } from "../i18n"
import { getTheme, setTheme, type ThemeName } from "../utils/theme"
import { releases } from "../content/releases"
import { useAppStore } from "../stores/app"

const props = defineProps<{ tab: "ui" | "about" | "changelog" }>()
const { t } = useI18n()
const appStore = useAppStore()
const { version } = storeToRefs(appStore)

const language = ref<AppLocale>(getStoredLocale())
const theme = ref<ThemeName>(getTheme())
const latestReleases = computed(() => releases.slice(0, 3))

function readUiConfigs(): Record<string, unknown> {
  try {
    const parsed = JSON.parse(localStorage.getItem(UI_CONFIGS_KEY) || "{}")
    return parsed && typeof parsed === "object" ? parsed as Record<string, unknown> : {}
  } catch { return {} }
}

const form = reactive({ tensorboard_url: String(readUiConfigs().tensorboard_url ?? "") })

const tabs = computed(() => [
  { key: "ui", to: "/settings/ui", label: t("settings.nav.ui") },
  { key: "about", to: "/settings/about", label: t("settings.nav.about") },
  { key: "changelog", to: "/settings/changelog", label: t("settings.nav.changelog") },
] as const)

function changeLanguage(value: AppLocale) {
  language.value = value
  setLocale(value)
}

function changeTheme(value: ThemeName) {
  theme.value = value
  setTheme(value)
}

function save() {
  const configs = readUiConfigs()
  configs.tensorboard_url = form.tensorboard_url.trim()
  localStorage.setItem(UI_CONFIGS_KEY, JSON.stringify(configs))
  ElMessage.success(t("settings.ui.saved"))
}

function reset() {
  form.tensorboard_url = ""
  const configs = readUiConfigs()
  delete configs.tensorboard_url
  localStorage.setItem(UI_CONFIGS_KEY, JSON.stringify(configs))
  ElMessage.success(t("settings.ui.resetDone"))
}
</script>

<template>
  <div class="settings-page">
    <header class="settings-page-header">
      <h1>{{ t("settings.title") }}</h1>
      <p>{{ t("settings.subtitle") }}</p>
    </header>
    <div class="settings-body">
      <nav class="settings-nav" aria-label="设置导航">
        <RouterLink v-for="item in tabs" :key="item.key" :to="item.to" class="settings-nav-link" :class="{ active: props.tab === item.key }">{{ item.label }}</RouterLink>
      </nav>
      <main class="settings-content">
        <template v-if="props.tab === 'ui'">
          <section class="settings-card">
            <h2>{{ t("settings.nav.ui") }}</h2>
            <label>{{ t("settings.ui.language") }}
              <select :value="language" @change="changeLanguage(($event.target as HTMLSelectElement).value as AppLocale)">
                <option v-for="locale in SUPPORTED_LOCALES" :key="locale.value" :value="locale.value">{{ locale.label }}</option>
              </select>
            </label>
            <div class="settings-field">
              <span class="settings-field-label">{{ t("settings.ui.theme") }}</span>
              <div class="segmented theme-switch" role="group" :aria-label="t('settings.ui.theme')">
                <button :class="{ active: theme === 'light' }" @click="changeTheme('light')">{{ t("settings.ui.themeLight") }}</button>
                <button :class="{ active: theme === 'dark' }" @click="changeTheme('dark')">{{ t("settings.ui.themeDark") }}</button>
              </div>
            </div>
            <label for="tensorboard-url">{{ t("settings.ui.tensorboardUrl") }}</label>
            <input id="tensorboard-url" v-model="form.tensorboard_url" :placeholder="t('settings.ui.tensorboardPlaceholder')">
            <small>可填写独立 TensorBoard 地址；留空时继续通过后端同源代理访问。</small>
            <div class="form-actions">
              <button class="primary-action" @click="save">{{ t("settings.ui.save") }}</button>
              <button class="secondary-action" @click="reset">{{ t("settings.ui.reset") }}</button>
            </div>
          </section>
          <section class="settings-card">
            <h2>LoRA 脚本工具</h2>
            <small>{{ t("settings.tools.note") }}</small>
          </section>
          <section class="settings-preview">
            <header>{{ t("settings.preview") }}</header>
            <div class="settings-preview-grid">
              <div class="settings-preview-col">
                <h3>{{ t("settings.nav.about") }}</h3>
                <p class="settings-about-line"><strong>{{ t("app.brand") }}</strong> <span class="version-badge">{{ version ? `v${version}` : "dev" }}</span></p>
                <p class="settings-about-desc">{{ t("settings.aboutDesc") }}</p>
                <RouterLink class="settings-more-link" to="/settings/about">{{ t("settings.nav.about") }} →</RouterLink>
              </div>
              <div class="settings-preview-col">
                <h3>{{ t("settings.nav.changelog") }}</h3>
                <ul class="settings-release-list">
                  <li v-for="release in latestReleases" :key="release.version"><time>{{ release.date }}</time><strong>{{ release.version }}</strong><span>{{ release.items[0] }}</span></li>
                </ul>
                <RouterLink class="settings-more-link" to="/settings/changelog">{{ t("settings.moreChangelog") }}</RouterLink>
              </div>
            </div>
          </section>
        </template>
        <AboutPage v-else-if="props.tab === 'about'" />
        <ChangelogPage v-else />
      </main>
    </div>
  </div>
</template>

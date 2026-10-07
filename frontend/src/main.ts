import { createApp } from "vue"
import { createPinia } from "pinia"
import { ElButton, ElCheckbox, ElConfigProvider, ElDialog, ElIcon, ElInput, ElInputNumber, ElOption, ElProgress, ElSelect, ElSwitch, vLoading } from "element-plus"
import "element-plus/theme-chalk/base.css"
import "element-plus/es/components/button/style/css"
import "element-plus/es/components/checkbox/style/css"
import "element-plus/es/components/config-provider/style/css"
import "element-plus/es/components/dialog/style/css"
import "element-plus/es/components/icon/style/css"
import "element-plus/es/components/input/style/css"
import "element-plus/es/components/input-number/style/css"
import "element-plus/es/components/message/style/css"
import "element-plus/es/components/message-box/style/css"
import "element-plus/es/components/option/style/css"
import "element-plus/es/components/progress/style/css"
import "element-plus/es/components/select/style/css"
import "element-plus/es/components/switch/style/css"
import "element-plus/es/components/loading/style/css"
import App from "./App.vue"
import { i18n } from "./i18n"
import router from "./router"
import { loadEngineSettings } from "./engines/settings"
import "./styles/tokens.css"
import "./styles/base.css"
import "./styles/home.css"
import "./styles/training.css"
import "./styles/schema-form.css"
import "./styles/workbench.css"
import "./styles/tasks.css"
import "./styles/dataset.css"
import "./styles/tagger.css"
import "./styles/settings.css"
import "./styles/anima-fast.css"
import "./styles/content-pages.css"
import "./styles/extensions.css"
import "./styles/dark-theme.css"

const app = createApp(App)
for (const component of [ElButton, ElCheckbox, ElConfigProvider, ElDialog, ElIcon, ElInput, ElInputNumber, ElOption, ElProgress, ElSelect, ElSwitch]) app.component(component.name!, component)
async function bootstrap() {
  // Hydrate before installing the router, which starts the initial navigation.
  try { await loadEngineSettings() } catch { /* App renders the shared error and retry action. */ }
  app.directive("loading", vLoading).use(createPinia()).use(router).use(i18n).mount("#app")
}
void bootstrap()

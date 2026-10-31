import { createApp, watchEffect } from 'vue'
import App from './App.vue'
import TrialApp from './TrialApp.vue'
import './style.css'
import { locale, t } from './i18n'

watchEffect(() => {
  document.title = t('Next Trainer 启动器')
  document.documentElement.lang = locale.value
})
createApp(new URLSearchParams(location.search).has('shell-trial') ? TrialApp : App).mount('#app')

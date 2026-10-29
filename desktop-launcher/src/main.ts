import { createApp } from 'vue'
import App from './App.vue'
import TrialApp from './TrialApp.vue'
import './style.css'

document.title = 'Next Trainer 启动器'
createApp(new URLSearchParams(location.search).has('shell-trial') ? TrialApp : App).mount('#app')

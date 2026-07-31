import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './style.css'
import { installActivityTracker } from './stores/activity'
import App from './App.vue'
import router from './router'

installActivityTracker()
createApp(App).use(router).use(ElementPlus).mount('#app')

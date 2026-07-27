import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'
import './style.css'
import { formatDate } from './format'

const app = createApp(App)
for (const [key, component] of Object.entries(ElementPlusIconsVue)) app.component(key, component)
app.use(ElementPlus)
app.config.globalProperties.$dt = formatDate
app.use(router)
app.mount('#app')

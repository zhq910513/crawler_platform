import { createRouter, createWebHistory } from 'vue-router'
import { authState, isAdmin } from './auth'
import Login from './views/Login.vue'
import MainLayout from './layouts/MainLayout.vue'
import Dashboard from './views/Dashboard.vue'
import Tasks from './views/Tasks.vue'
import TaskEditor from './views/TaskEditor.vue'
import Runs from './views/Runs.vue'
import RunDetail from './views/RunDetail.vue'
import Servers from './views/Servers.vue'
import Projects from './views/Projects.vue'
import Users from './views/Users.vue'
import Operations from './views/Operations.vue'
import Settings from './views/Settings.vue'

const routes = [
  { path: '/login', component: Login, meta: { public: true } },
  {
    path: '/',
    component: MainLayout,
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', component: Dashboard, meta: { title: '首页', admin: true } },
      { path: 'tasks', component: Tasks, meta: { title: '任务列表' } },
      { path: 'tasks/new', component: TaskEditor, meta: { title: '新增任务', admin: true } },
      { path: 'tasks/:id/edit', component: TaskEditor, meta: { title: '编辑任务', admin: true } },
      { path: 'runs', component: Runs, meta: { title: '执行记录' } },
      { path: 'runs/:id', component: RunDetail, meta: { title: '运行详情' } },
      { path: 'servers', component: Servers, meta: { title: '服务器监控', admin: true } },
      { path: 'projects', component: Projects, meta: { title: '项目与镜像', admin: true } },
      { path: 'operations', component: Operations, meta: { title: '操作日志', admin: true } },
      { path: 'users', component: Users, meta: { title: '用户管理', admin: true } },
      { path: 'settings', component: Settings, meta: { title: '系统设置', admin: true } }
    ]
  }
]

const router = createRouter({ history: createWebHistory(), routes })
router.beforeEach((to) => {
  if (!to.meta.public && !authState.token) return '/login'
  if (to.meta.admin && !isAdmin.value) return '/tasks'
  if (to.path === '/login' && authState.token) return '/dashboard'
})

export default router

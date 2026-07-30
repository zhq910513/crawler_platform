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
import ProjectDetail from './views/ProjectDetail.vue'
import Companies from './views/Companies.vue'
import Releases from './views/Releases.vue'
import Users from './views/Users.vue'
import Operations from './views/Operations.vue'
import Settings from './views/Settings.vue'

const routes = [
  { path: '/login', component: Login, meta: { public: true } },
  { path: '/', component: MainLayout, redirect: '/dashboard', children: [
    { path: 'dashboard', component: Dashboard, meta: { title: '运行总览' } },
    { path: 'tasks', component: Tasks, meta: { title: '任务管理' } },
    { path: 'tasks/new', component: TaskEditor, meta: { title: '新增任务' } },
    { path: 'tasks/:id/edit', component: TaskEditor, meta: { title: '编辑任务' } },
    { path: 'runs', component: Runs, meta: { title: '执行记录' } },
    { path: 'runs/:id', component: RunDetail, meta: { title: '运行详情' } },
    { path: 'projects', component: Projects, meta: { title: '项目管理' } },
    { path: 'projects/:id', component: ProjectDetail, meta: { title: '项目详情' } },
    { path: 'companies', component: Companies, meta: { title: '公司与成员' } },
    { path: 'releases', component: Releases, meta: { title: '爬虫发布' } },
    { path: 'servers', component: Servers, meta: { title: 'Agent 节点', admin: true } },
    { path: 'operations', component: Operations, meta: { title: '操作日志', admin: true } },
    { path: 'users', component: Users, meta: { title: '用户管理', admin: true } },
    { path: 'settings', component: Settings, meta: { title: '系统设置', admin: true } }
  ]}
]
const router = createRouter({ history: createWebHistory(), routes })
router.beforeEach(to => {
  if (!to.meta.public && !authState.token) return '/login'
  if (to.meta.admin && !isAdmin.value) return '/dashboard'
  if (to.path === '/login' && authState.token) return '/dashboard'
})
export default router

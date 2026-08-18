import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { sessionState } from './stores/session'

const loginView = () => import('./views/LoginPage.vue')
const mainLayout = () => import('./layouts/MainLayout.vue')
const dashboardView = () => import('./views/DashboardPage.vue')
const runningCenterView = () => import('./views/RunningCenterPage.vue')
const companiesView = () => import('./views/CompaniesPage.vue')
const usersView = () => import('./views/UsersPage.vue')
const resourcesView = () => import('./views/CompanyResourcesPage.vue')
const serversView = () => import('./views/ServersPage.vue')
const projectPublishView = () => import('./views/ProjectPublishPage.vue')
const projectsView = () => import('./views/ProjectsPage.vue')
const tasksView = () => import('./views/TasksPage.vue')
const runsView = () => import('./views/RunsPage.vue')
const platformsView = () => import('./views/TargetPlatformsPage.vue')
const accountsView = () => import('./views/AccountCredentialsPage.vue')
const operationsView = () => import('./views/OperationsPage.vue')
const settingsView = () => import('./views/SettingsPage.vue')

const commonPreloaders = [
  runningCenterView,
  projectPublishView,
  projectsView,
  tasksView,
  runsView,
  serversView,
  accountsView,
  resourcesView,
  platformsView,
]
const adminPreloaders = [dashboardView, companiesView, usersView, operationsView, settingsView]
const preloaded = new Set<() => Promise<unknown>>()

type IdleWindow = Window & { requestIdleCallback?: (callback: () => void, options?: { timeout?: number }) => number }

function runWhenIdle(callback: () => void) {
  if (typeof window === 'undefined') return
  const requestIdleCallback = (window as IdleWindow).requestIdleCallback
  if (requestIdleCallback) requestIdleCallback(callback, { timeout: 1800 })
  else window.setTimeout(callback, 300)
}

export function preloadAuthenticatedRoutes(isSuperAdmin = false) {
  const loaders = isSuperAdmin ? [...commonPreloaders, ...adminPreloaders] : commonPreloaders
  runWhenIdle(() => {
    let index = 0
    const preloadNext = () => {
      const loader = loaders[index]
      index += 1
      if (!loader) return
      if (!preloaded.has(loader)) {
        preloaded.add(loader)
        void loader().catch(() => undefined)
      }
      window.setTimeout(preloadNext, 80)
    }
    preloadNext()
  })
}

const keepAliveMeta = { keepAlive: true }
const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: loginView, meta: { title: '登录' } },
  { path: '/', component: mainLayout, children: [
    { path: '', redirect: () => sessionState.user?.isSuperAdmin ? '/dashboard' : '/running-center' },
    { path: 'dashboard', name: 'dashboard', component: dashboardView, meta: { title: '运行总览', adminOnly: true, ...keepAliveMeta } },
    { path: 'running-center', name: 'running-center', component: runningCenterView, meta: { title: '运行中心', ...keepAliveMeta } },
    { path: 'companies', name: 'companies', component: companiesView, meta: { title: '公司管理', adminOnly: true, ...keepAliveMeta } },
    { path: 'users', name: 'users', component: usersView, meta: { title: '用户权限', adminOnly: true, ...keepAliveMeta } },
    { path: 'resources', name: 'resources', component: resourcesView, meta: { title: '数据资源配置', ...keepAliveMeta } },
    { path: 'servers', name: 'servers', component: serversView, meta: { title: '执行节点', ...keepAliveMeta } },
    { path: 'project-publish', name: 'project-publish', component: projectPublishView, meta: { title: '项目发布', ...keepAliveMeta } },
    { path: 'projects', name: 'projects', component: projectsView, meta: { title: '项目版本', ...keepAliveMeta } },
    { path: 'tasks', name: 'tasks', component: tasksView, meta: { title: '任务编排', ...keepAliveMeta } },
    { path: 'runs', name: 'runs', component: runsView, meta: { title: '执行记录', ...keepAliveMeta } },
    { path: 'platforms', name: 'platforms', component: platformsView, meta: { title: '采集目标', ...keepAliveMeta } },
    { path: 'accounts', name: 'accounts', component: accountsView, meta: { title: '账号资源', ...keepAliveMeta } },
    { path: 'operations', name: 'operations', component: operationsView, meta: { title: '操作审计', adminOnly: true, ...keepAliveMeta } },
    { path: 'settings', name: 'settings', component: settingsView, meta: { title: '系统设置', adminOnly: true, ...keepAliveMeta } },
  ] },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to) => {
  document.title = `${String(to.meta.title || '首页')} - 爬虫管理平台`
  if (to.path !== '/login' && !sessionState.token) return '/login'
  if (to.meta.adminOnly && !sessionState.user?.isSuperAdmin) return '/running-center'
  return true
})

export default router

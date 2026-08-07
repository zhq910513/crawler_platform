import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { sessionState } from './stores/session'

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: () => import('./views/LoginPage.vue'), meta: { title: '登录' } },
  { path: '/', component: () => import('./layouts/MainLayout.vue'), children: [
    { path: '', redirect: () => sessionState.user?.isSuperAdmin ? '/dashboard' : '/projects' },
    { path: 'dashboard', component: () => import('./views/DashboardPage.vue'), meta: { title: '运行总览', adminOnly: true } },
    { path: 'companies', component: () => import('./views/CompaniesPage.vue'), meta: { title: '公司管理', adminOnly: true } },
    { path: 'users', component: () => import('./views/UsersPage.vue'), meta: { title: '用户管理', adminOnly: true } },
    { path: 'resources', component: () => import('./views/CompanyResourcesPage.vue'), meta: { title: '数据库配置' } },
    { path: 'servers', component: () => import('./views/ServersPage.vue'), meta: { title: '执行节点' } },
    { path: 'projects', component: () => import('./views/ProjectsPage.vue'), meta: { title: '项目管理' } },
    { path: 'tasks', component: () => import('./views/TasksPage.vue'), meta: { title: '任务调度' } },
    { path: 'runs', component: () => import('./views/RunsPage.vue'), meta: { title: '执行记录' } },
    { path: 'platforms', component: () => import('./views/TargetPlatformsPage.vue'), meta: { title: '采集平台' } },
    { path: 'accounts', component: () => import('./views/AccountCredentialsPage.vue'), meta: { title: '平台账号' } },
    { path: 'operations', component: () => import('./views/OperationsPage.vue'), meta: { title: '操作日志', adminOnly: true } },
    { path: 'settings', component: () => import('./views/SettingsPage.vue'), meta: { title: '系统设置', adminOnly: true } },
  ] },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to) => {
  document.title = `${String(to.meta.title || '首页')} - 爬虫管理平台`
  if (to.path !== '/login' && !sessionState.token) return '/login'
  if (to.meta.adminOnly && !sessionState.user?.isSuperAdmin) return '/projects'
  return true
})

export default router

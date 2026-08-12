import { Coin, DataAnalysis, FolderOpened, Guide, Histogram, Key, List, Monitor, OfficeBuilding, Operation, Setting, UploadFilled, User } from '@element-plus/icons-vue'

export type NavigationItem = {
  path: string
  title: string
  subtitle: string
  adminOnly?: boolean
  icon: unknown
  flow?: string
}

export type NavigationGroup = {
  key: string
  title: string
  items: NavigationItem[]
}

export const navigationGroups: NavigationGroup[] = [
  {
    key: 'business',
    title: '经营驾驶舱',
    items: [
      { path: '/dashboard', title: '运行总览', subtitle: '整体运行情况与待处理事项', adminOnly: true, icon: Histogram, flow: 'business' },
      { path: '/running-center', title: '运行中心', subtitle: '按公司、项目、任务查看运行状态与处理建议', icon: DataAnalysis, flow: 'business' },
    ],
  },
  {
    key: 'delivery',
    title: '项目交付',
    items: [
      { path: '/companies', title: '公司管理', subtitle: '公司边界与基础信息管理', adminOnly: true, icon: OfficeBuilding, flow: 'delivery' },
      { path: '/servers', title: '服务器管理', subtitle: '服务器接入、健康、容量与部署状态', icon: Monitor, flow: 'delivery' },
      { path: '/project-publish', title: '项目发布', subtitle: '选择公司、服务器和代码仓库后发布爬虫项目', icon: UploadFilled, flow: 'delivery' },
      { path: '/projects', title: '项目版本', subtitle: '已发布项目、版本和服务器部署结果', icon: FolderOpened, flow: 'delivery' },
      { path: '/tasks', title: '任务编排', subtitle: '任务创建、账号分配、排程与手动执行', icon: List, flow: 'delivery' },
      { path: '/runs', title: '执行记录', subtitle: '任务执行过程、日志与失败诊断', icon: DataAnalysis, flow: 'delivery' },
    ],
  },
  {
    key: 'resources',
    title: '资源准备',
    items: [
      { path: '/resources', title: '数据库配置', subtitle: '公司数据库、缓存与存储资源', icon: Coin, flow: 'resources' },
      { path: '/platforms', title: '采集目标', subtitle: '被采集网站与系统的接入准备情况', icon: Guide, flow: 'resources' },
      { path: '/accounts', title: '账号资源', subtitle: '采集账号健康、对象绑定与占用情况', icon: Key, flow: 'resources' },
    ],
  },
  {
    key: 'governance',
    title: '系统治理',
    items: [
      { path: '/users', title: '用户权限', subtitle: '用户、角色与登录安全', adminOnly: true, icon: User, flow: 'governance' },
      { path: '/operations', title: '操作审计', subtitle: '关键操作审计记录', adminOnly: true, icon: Operation, flow: 'governance' },
      { path: '/settings', title: '系统设置', subtitle: '控制端公网回调地址、通知渠道与系统配置', adminOnly: true, icon: Setting, flow: 'governance' },
    ],
  },
]

export const navigationItems = navigationGroups.flatMap((group) => group.items)

export function visibleNavigationGroups(isSuperAdmin: boolean) {
  return navigationGroups
    .map((group) => ({ ...group, items: group.items.filter((item) => !item.adminOnly || isSuperAdmin) }))
    .filter((group) => group.items.length > 0)
}

export function findNavigationItem(path: string) {
  return navigationItems.find((item) => item.path === path)
}


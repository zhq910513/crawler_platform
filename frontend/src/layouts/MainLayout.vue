<template>
  <el-container class="layout">
    <el-aside width="230px" class="aside">
      <div class="brand">爬虫管理平台</div>
      <el-menu router :default-active="$route.path" background-color="#111827" text-color="#cbd5e1" active-text-color="#ffffff">
        <el-menu-item v-for="item in visibleMenus" :key="item.path" :index="item.path">{{ item.title }}</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div>{{ $route.meta.title }}</div>
        <div class="user-box">
          <span>{{ sessionState.user?.nickName }}</span>
          <el-button size="small" @click="logout">退出</el-button>
        </div>
      </el-header>
      <el-main><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { deleteSession } from '../api/sessions'
import { clearSession, sessionState } from '../stores/session'

const router = useRouter()
const menus = [
  { path: '/dashboard', title: '运行总览', adminOnly: true },
  { path: '/companies', title: '公司配置', adminOnly: true },
  { path: '/users', title: '用户管理', adminOnly: true },
  { path: '/servers', title: 'Agent 节点', adminOnly: false },
  { path: '/projects', title: '项目管理', adminOnly: false },
  { path: '/tasks', title: '任务调度', adminOnly: false },
  { path: '/runs', title: '执行记录', adminOnly: false },
  { path: '/operations', title: '操作日志', adminOnly: true },
  { path: '/settings', title: '系统设置', adminOnly: true },
]
const visibleMenus = computed(() => menus.filter((item) => !item.adminOnly || sessionState.user?.isSuperAdmin))
async function logout() {
  const sessionId = sessionState.sessionId
  if (sessionId) await deleteSession(sessionId).catch(() => undefined)
  clearSession()
  await router.push('/login')
}
</script>

<style scoped>
.layout { min-height: 100vh; }
.aside { background: #111827; }
.brand { color: #fff; font-size: 20px; font-weight: 700; height: 56px; display: flex; align-items: center; padding-left: 22px; border-bottom: 1px solid #243142; }
.header { background: #fff; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #e5e7eb; font-size: 16px; font-weight: 600; }
.user-box { display: flex; gap: 12px; align-items: center; font-weight: 400; }
.el-menu { border-right: none; }
</style>

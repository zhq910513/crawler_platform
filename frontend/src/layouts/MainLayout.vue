<template>
  <el-container class="layout">
    <el-aside width="230px" class="aside">
      <div class="brand">爬虫管理平台</div>
      <el-menu router :default-active="$route.path" background-color="#111827" text-color="#cbd5e1" active-text-color="#ffffff">
        <el-menu-item v-for="item in visibleMenus" :key="item.path" :index="item.path">{{ item.title }}</el-menu-item>
      </el-menu>
      <div class="version-box">
        <div :title="frontendVersionTitle">前端 v{{ frontendVersion.version }}</div>
        <div :title="backendVersionTitle">后端 v{{ backendVersion?.version || '-' }}</div>
      </div>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div>{{ $route.meta.title }}</div>
        <div class="user-box">
          <el-tag v-if="sessionState.user?.passwordChangeRequired" type="warning">需修改密码</el-tag>
          <span>{{ sessionState.user?.nickName }}</span>
          <el-button size="small" @click="openPasswordDialog">修改密码</el-button>
          <el-button size="small" @click="logout">退出</el-button>
        </div>
      </el-header>
      <el-main><router-view /></el-main>
    </el-container>
  </el-container>

  <el-dialog v-model="passwordDialogVisible" title="修改密码" width="460px" :close-on-click-modal="!passwordRequired" :show-close="!passwordRequired">
    <el-alert v-if="passwordRequired" title="当前账号必须先修改密码，修改成功后需要重新登录。" type="warning" show-icon :closable="false" class="password-alert" />
    <el-form label-position="top">
      <el-form-item label="当前密码"><el-input v-model="passwordForm.oldPassword" type="password" autocomplete="current-password" show-password /></el-form-item>
      <el-form-item label="新密码"><el-input v-model="passwordForm.newPassword" type="password" autocomplete="new-password" show-password /></el-form-item>
      <el-form-item label="确认新密码"><el-input v-model="passwordForm.confirmPassword" type="password" autocomplete="new-password" show-password /></el-form-item>
    </el-form>
    <template #footer>
      <el-button v-if="!passwordRequired" @click="passwordDialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="passwordSaving" @click="submitPasswordChange">保存并重新登录</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { changeOwnPassword } from '../api/platform'
import { getBackendHealth, getFrontendVersion } from '../api/health'
import { frontendBuildVersion } from '../config/version'
import type { BackendHealthData, SystemVersionInfo } from '../types/api'
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
const passwordDialogVisible = ref(false)
const passwordSaving = ref(false)
const passwordRequired = computed(() => Boolean(sessionState.user?.passwordChangeRequired))
const passwordForm = reactive({ oldPassword: '', newPassword: '', confirmPassword: '' })
const frontendVersion = ref<SystemVersionInfo>(frontendBuildVersion)
const backendVersion = ref<BackendHealthData | null>(null)
const frontendVersionTitle = computed(() => `commit: ${frontendVersion.value.gitCommit}\nbuild: ${frontendVersion.value.buildTime}`)
const backendVersionTitle = computed(() => backendVersion.value ? `commit: ${backendVersion.value.gitCommit}\nbuild: ${backendVersion.value.buildTime}\nmigration: ${backendVersion.value.migrationVersion}` : '后端版本加载中')

onMounted(() => {
  if (passwordRequired.value) passwordDialogVisible.value = true
  loadVersionInfo()
})

async function loadVersionInfo() {
  frontendVersion.value = await getFrontendVersion()
  backendVersion.value = await getBackendHealth().catch(() => null)
}

function openPasswordDialog() {
  passwordForm.oldPassword = ''
  passwordForm.newPassword = ''
  passwordForm.confirmPassword = ''
  passwordDialogVisible.value = true
}

async function submitPasswordChange() {
  passwordSaving.value = true
  try {
    await changeOwnPassword(passwordForm)
    ElMessage.success('密码已修改，请重新登录')
    clearSession()
    await router.push('/login')
  } finally {
    passwordSaving.value = false
  }
}

async function logout() {
  const sessionId = sessionState.sessionId
  if (sessionId) await deleteSession(sessionId).catch(() => undefined)
  clearSession()
  await router.push('/login')
}
</script>

<style scoped>
.layout { min-height: 100vh; }
.aside { background: #111827; position: relative; }
.brand { color: #fff; font-size: 20px; font-weight: 700; height: 56px; display: flex; align-items: center; padding-left: 22px; border-bottom: 1px solid #243142; }
.header { background: #fff; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #e5e7eb; font-size: 16px; font-weight: 600; }
.user-box { display: flex; gap: 12px; align-items: center; font-weight: 400; }
.password-alert { margin-bottom: 12px; }
.el-menu { border-right: none; }
.version-box { position: absolute; left: 16px; right: 16px; bottom: 14px; color: #94a3b8; font-size: 12px; line-height: 1.7; border-top: 1px solid #243142; padding-top: 10px; word-break: break-all; }
</style>

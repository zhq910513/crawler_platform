<template>
  <el-container class="layout-shell">
    <el-aside width="268px" class="layout-aside">
      <div class="brand-panel">
        <div class="brand-mark">爬</div>
        <div>
          <div class="brand-title">爬虫管理平台</div>
          <div class="brand-subtitle">项目交付 · 运行治理</div>
        </div>
      </div>
      <div class="quick-actions">
        <el-button type="primary" plain @click="router.push('/project-publish')">发布项目</el-button>
        <el-button plain @click="router.push('/servers?openOnboarding=1')">新增服务器</el-button>
      </div>
      <el-menu router :default-active="activePath" class="side-menu">
        <el-sub-menu v-for="group in visibleGroups" :key="group.key" :index="group.key">
          <template #title><span class="group-title">{{ group.title }}</span></template>
          <el-menu-item v-for="item in group.items" :key="item.path" :index="item.path">
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.title }}</span>
          </el-menu-item>
        </el-sub-menu>
      </el-menu>
      <div class="version-card">
        <div class="version-label">当前版本</div>
        <div class="version-value">v{{ frontendVersion.version }}</div>
      </div>
    </el-aside>
    <el-container class="layout-main">
      <el-header class="topbar">
        <div>
          <div class="page-title">{{ currentNav?.title || $route.meta.title }}</div>
          <div class="page-subtitle">{{ currentNav?.subtitle || routeSubtitle }}</div>
        </div>
        <div class="user-box">
          <el-tag v-if="sessionState.user?.passwordChangeRequired" type="warning" effect="light">需修改密码</el-tag>
          <span class="user-name">{{ sessionState.user?.nickName || sessionState.user?.userName }}</span>
          <el-button size="small" @click="openPasswordDialog">修改密码</el-button>
          <el-button size="small" plain @click="logout">退出</el-button>
        </div>
      </el-header>
      <div v-if="currentFlowItems.length > 1 && !passwordRequired" class="flow-strip">
        <span class="flow-label">当前流程</span>
        <el-button v-for="item in currentFlowItems" :key="item.path" size="small" :type="item.path === activePath ? 'primary' : 'default'" plain @click="router.push(item.path)">{{ item.title }}</el-button>
      </div>
      <el-main class="content-wrap">
        <div v-if="passwordRequired" class="forced-password-panel">请先完成密码修改。完成后系统会要求重新登录，再进入业务页面。</div>
        <router-view v-else v-slot="{ Component, route }">
          <KeepAlive :max="12">
            <component :is="Component" v-if="route.meta.keepAlive" :key="route.name || route.path" />
          </KeepAlive>
          <component :is="Component" v-if="!route.meta.keepAlive" :key="route.fullPath" />
        </router-view>
      </el-main>
    </el-container>
  </el-container>
  <ConfigAssistantDrawer />

  <el-dialog v-model="passwordDialogVisible" title="修改密码" width="460px" :close-on-click-modal="!passwordRequired" :close-on-press-escape="!passwordRequired" :show-close="!passwordRequired">
    <el-form label-position="top">
      <el-alert v-if="passwordError" class="password-alert" type="error" :title="passwordError" show-icon :closable="false" />
      <el-form-item label="当前密码"><el-input v-model="passwordForm.oldPassword" type="password" autocomplete="current-password" show-password /></el-form-item>
      <el-form-item label="新密码"><el-input v-model="passwordForm.newPassword" type="password" autocomplete="new-password" show-password /></el-form-item>
      <el-form-item label="确认新密码"><el-input v-model="passwordForm.confirmPassword" type="password" autocomplete="new-password" show-password /></el-form-item>
      <div class="password-help">新密码至少 8 位，必须包含大小写字母、数字和特殊字符，且不能与当前密码相同。</div>
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
import { preloadAuthenticatedRoutes } from '../router'
import { changeOwnPassword } from '../api/platform'
import { apiErrorData } from '../api/client'
import { getBackendHealth, getFrontendVersion } from '../api/health'
import { frontendBuildVersion } from '../config/version'
import { findNavigationItem, flowItems, visibleNavigationGroups } from '../config/navigation'
import type { BackendHealthData, SystemVersionInfo } from '../types/api'
import { deleteSession } from '../api/sessions'
import { clearSession, markPasswordChangeReloginInProgress, sessionState } from '../stores/session'
import ConfigAssistantDrawer from '../components/ConfigAssistantDrawer.vue'

const router = useRouter()
const visibleGroups = computed(() => visibleNavigationGroups(Boolean(sessionState.user?.isSuperAdmin)))
const activePath = computed(() => router.currentRoute.value.path)
const currentNav = computed(() => findNavigationItem(activePath.value))
const currentFlowItems = computed(() => flowItems(currentNav.value?.flow, Boolean(sessionState.user?.isSuperAdmin)))
const routeSubtitle = computed(() => '爬虫项目统一交付与运行管理')
const passwordDialogVisible = ref(false)
const passwordSaving = ref(false)
const passwordRequired = computed(() => Boolean(sessionState.user?.passwordChangeRequired))
const passwordForm = reactive({ oldPassword: '', newPassword: '', confirmPassword: '' })
const passwordError = ref('')
const passwordPolicyText = '新密码至少 8 位，必须包含大小写字母、数字和特殊字符，且不能与当前密码相同。'
const frontendVersion = ref<SystemVersionInfo>(frontendBuildVersion)
const backendVersion = ref<BackendHealthData | null>(null)

onMounted(() => {
  if (passwordRequired.value) passwordDialogVisible.value = true
  loadVersionInfo()
  preloadAuthenticatedRoutes(Boolean(sessionState.user?.isSuperAdmin))
})

async function loadVersionInfo() {
  frontendVersion.value = await getFrontendVersion()
  backendVersion.value = await getBackendHealth().catch(() => null)
}

function openPasswordDialog() {
  passwordForm.oldPassword = ''
  passwordForm.newPassword = ''
  passwordForm.confirmPassword = ''
  passwordError.value = ''
  passwordDialogVisible.value = true
}

function passwordFormProblem() {
  if (!passwordForm.oldPassword) return '请输入当前密码'
  if (passwordForm.newPassword !== passwordForm.confirmPassword) return '两次输入的新密码不一致'
  if (passwordForm.newPassword === passwordForm.oldPassword) return '新密码不能与当前密码相同'
  if (!/^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,200}$/.test(passwordForm.newPassword)) return passwordPolicyText
  return ''
}

async function submitPasswordChange() {
  passwordError.value = passwordFormProblem()
  if (passwordError.value) {
    ElMessage.error(passwordError.value)
    return
  }
  passwordSaving.value = true
  try {
    await changeOwnPassword(passwordForm)
    markPasswordChangeReloginInProgress()
    ElMessage.success('密码已修改，请重新登录')
    clearSession()
    await router.replace('/login')
  } catch (error) {
    const payload = apiErrorData<unknown>(error)
    const fallback = error instanceof Error ? error.message : '密码修改失败'
    passwordError.value = payload?.message || fallback
    ElMessage.error(passwordError.value)
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
.layout-shell { min-height: 100vh; background: #f4f7fb; }
.layout-aside { position: relative; display: flex; flex-direction: column; border-right: 1px solid rgba(148, 163, 184, 0.18); background: linear-gradient(180deg, #0f172a 0%, #111827 45%, #101827 100%); box-shadow: 12px 0 32px rgba(15, 23, 42, 0.08); }
.brand-panel { display: flex; align-items: center; gap: 12px; height: 74px; padding: 0 20px; color: #fff; }
.brand-mark { display: flex; align-items: center; justify-content: center; width: 38px; height: 38px; border-radius: 12px; background: linear-gradient(135deg, #3b82f6, #06b6d4); font-size: 20px; font-weight: 800; box-shadow: 0 12px 28px rgba(37, 99, 235, 0.3); }
.brand-title { font-size: 18px; font-weight: 800; letter-spacing: 0.5px; }
.brand-subtitle { margin-top: 3px; color: #94a3b8; font-size: 12px; }
.quick-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 0 14px 10px; }
.quick-actions .el-button { width: 100%; margin: 0; }
.side-menu { flex: 1; padding: 8px 10px; border-right: none; background: transparent; overflow-y: auto; }
.side-menu :deep(.el-sub-menu__title) { height: 38px; padding: 0 12px !important; color: #94a3b8; border-radius: 10px; }
.side-menu :deep(.el-sub-menu__title:hover) { background: rgba(59, 130, 246, 0.1); color: #e2e8f0; }
.group-title { font-size: 12px; font-weight: 800; letter-spacing: 0.04em; }
.side-menu :deep(.el-menu) { background: transparent; }
.side-menu :deep(.el-menu-item) { height: 42px; margin: 4px 0; border-radius: 12px; color: #cbd5e1; font-size: 14px; }
.side-menu :deep(.el-menu-item .el-icon) { margin-right: 12px; font-size: 17px; }
.side-menu :deep(.el-menu-item:hover) { background: rgba(59, 130, 246, 0.13); color: #fff; }
.side-menu :deep(.el-menu-item.is-active) { background: linear-gradient(135deg, #2563eb, #0ea5e9); color: #fff; box-shadow: 0 12px 28px rgba(37, 99, 235, 0.28); }
.version-card { margin: 12px 16px 18px; padding: 12px 14px; border: 1px solid rgba(148, 163, 184, 0.16); border-radius: 14px; background: rgba(15, 23, 42, 0.62); color: #dbeafe; }
.version-label { color: #94a3b8; font-size: 12px; }
.version-value { margin-top: 3px; font-size: 15px; font-weight: 700; }
.layout-main { min-width: 0; }
.topbar { display: flex; align-items: center; justify-content: space-between; height: 72px; padding: 0 28px; border-bottom: 1px solid #e6ebf2; background: rgba(255, 255, 255, 0.88); backdrop-filter: blur(10px); }
.page-title { color: #111827; font-size: 20px; font-weight: 800; }
.page-subtitle { margin-top: 4px; color: #7b8798; font-size: 12px; font-weight: 400; }
.flow-strip { display: flex; align-items: center; gap: 8px; padding: 10px 28px; border-bottom: 1px solid #e6ebf2; background: #fff; }
.flow-label { margin-right: 4px; color: #64748b; font-size: 12px; font-weight: 700; }
.user-box { display: flex; gap: 12px; align-items: center; color: #334155; }
.user-name { font-weight: 600; }
.password-alert { margin-bottom: 14px; }
.password-help { margin-top: -4px; color: #64748b; font-size: 12px; line-height: 1.6; }
.content-wrap { padding: 22px 24px 28px; }
.forced-password-panel { display: flex; align-items: center; justify-content: center; min-height: 360px; border: 1px dashed #f59e0b; border-radius: 16px; background: #fffbeb; color: #92400e; font-weight: 700; }
@media (max-width: 980px) { .layout-aside { width: 226px !important; } .topbar { padding: 0 18px; } .content-wrap { padding: 16px; } .quick-actions { grid-template-columns: 1fr; } }
</style>

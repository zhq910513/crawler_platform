<template>
  <div class="page-card servers-page">
    <div class="toolbar hero-toolbar">
      <div>
        <h3>执行节点</h3>
        <p class="muted">接入节点后，平台会在这些节点上运行爬虫任务。</p>
      </div>
      <div>
        <el-button type="primary" @click="openOnboarding">接入节点</el-button>
        <el-button v-if="sessionState.user?.isSuperAdmin" @click="dialogVisible = true">手工新增</el-button>
        <el-button :loading="loading" @click="refreshPage">刷新</el-button>
      </div>
    </div>

    <el-table :data="rows" stripe>
      <el-table-column label="执行节点" min-width="220">
        <template #default="s">
          <div class="server-name">{{ s.row.serverName }}</div>
          <div class="muted">{{ serverAddressText(s.row) }}</div>
        </template>
      </el-table-column>
      <el-table-column label="状态" min-width="130">
        <template #default="s">
          <el-tag :type="nodeStatusTag(s.row)" effect="light">{{ nodeStatusText(s.row) }}</el-tag>
          <div v-if="nodeStatusHint(s.row)" class="muted node-hint">{{ nodeStatusHint(s.row) }}</div>
        </template>
      </el-table-column>
      <el-table-column label="资源" min-width="210">
        <template #default="s">
          <template v-if="hasRuntimeMetrics(s.row)">
            <div>CPU {{ metricText(s.row.metrics?.cpuUsage) }} · 内存 {{ metricText(s.row.metrics?.memoryUsage) }}</div>
            <div class="muted">磁盘 {{ metricText(s.row.metrics?.diskUsage) }} · 文件数 {{ metricText(s.row.metrics?.inodeUsage) }}</div>
          </template>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="运行任务" width="100">
        <template #default="s">{{ hasRuntimeMetrics(s.row) ? (s.row.metrics?.runningContainers ?? 0) : '-' }}</template>
      </el-table-column>
      <el-table-column label="最后心跳" min-width="170">
        <template #default="s">{{ formatTime(s.row.agentLastHeartbeatAt || s.row.metrics?.lastHeartbeatAt) }}</template>
      </el-table-column>
      <el-table-column label="最近异常" min-width="220">
        <template #default="s">{{ s.row.metrics?.decommissionError || s.row.metrics?.lastError || s.row.agentLastError || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="190" fixed="right">
        <template #default="s">
          <el-button v-if="canRejoinNode(s.row)" link type="primary" :disabled="s.row.lifecycleStatus === 'DRAINING' || s.row.lifecycleStatus === 'DECOMMISSIONING'" @click="rejoinNode(s.row)">重新接入</el-button>
          <el-button link type="danger" :disabled="s.row.lifecycleStatus === 'DRAINING' || s.row.lifecycleStatus === 'DECOMMISSIONING'" @click="cleanupNode(s.row)">移除</el-button>
        </template>
      </el-table-column>
    </el-table>


    <div class="join-invitations-card">
      <div class="section-header">
        <div>
          <h4>接入记录</h4>
          <p class="muted">仅保留待接入、接入中和接入失败记录；清理后的记录不再显示。</p>
        </div>
      </div>
      <el-table :data="joinInvitations.slice(0, 8)" size="small" stripe>
        <el-table-column label="节点" min-width="180"><template #default="s">{{ s.row.server_name || s.row.serverName || '-' }}</template></el-table-column>
        <el-table-column label="状态" width="110"><template #default="s"><el-tag effect="light">{{ invitationStatusText(s.row) }}</el-tag></template></el-table-column>
        <el-table-column label="结果" min-width="260"><template #default="s">{{ invitationResultText(s.row) }}</template></el-table-column>
        <el-table-column label="更新时间" min-width="170"><template #default="s">{{ formatTime(s.row.updated_at || s.row.updatedAt || s.row.created_at || s.row.createdAt) }}</template></el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="s">
            <el-button v-if="canCleanupInvitation(s.row)" link type="danger" @click="cleanupInvitation(s.row)">清理记录</el-button>
            <span v-else class="muted">节点列表处理</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="onboardingVisible" title="接入执行节点" width="860px" class="onboarding-dialog">
      <el-steps :active="onboardingStepActive" simple class="wizard-steps">
        <el-step title="填写节点信息" />
        <el-step title="复制命令执行" />
        <el-step title="等待节点上线" />
      </el-steps>

      <el-alert class="guide-alert" type="info" :closable="false" show-icon title="接入凭证会由系统自动生成并写入安装命令，不需要单独复制。" />

      <div v-if="controlPreflight" class="preflight-panel" :class="`preflight-${controlPreflight.status.toLowerCase()}`">
        <div class="preflight-header">
          <div>
            <div class="preflight-title">接入前检查</div>
            <div class="muted">自动检测：已确认异常 {{ controlPreflight.blockingCount }}，运行提醒 {{ controlPreflight.warningCount }}，待场景验证 {{ controlPreflight.pendingCount }}。待场景项无需提前人工确认。</div>
          </div>
          <el-tag :type="preflightTag(controlPreflight.status)" effect="light">{{ preflightLabel(controlPreflight.status) }}</el-tag>
        </div>
        <div v-if="controlPreflight.nextAction" class="check-suggestion">下一步：{{ controlPreflight.nextAction }}</div>
        <el-button size="small" @click="goDashboardPreflight">查看平台状态</el-button>
      </div>

      <el-form label-position="top" class="onboarding-form">
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="公司"><el-select v-if="sessionState.user?.isSuperAdmin" v-model="joinForm.companyId" @change="applyAutoCodes"><el-option v-for="company in companies" :key="company.companyId" :label="company.companyName" :value="company.companyId" /></el-select><el-input v-else :model-value="currentCompanyName" disabled /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="接入场景"><el-radio-group v-model="joinForm.installTarget" @change="applyInstallTarget"><el-radio-button label="REMOTE">远程节点</el-radio-button><el-radio-button label="LOCAL">本机测试</el-radio-button></el-radio-group></el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="节点名称"><el-input v-model="joinForm.serverName" placeholder="例如：上海执行节点01" @blur="applyAutoCodes" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="同时运行任务上限"><el-input-number v-model="joinForm.maxContainerSlots" :min="1" :max="100" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="工作目录"><el-input v-model="joinForm.workDir" /></el-form-item>
        <el-checkbox v-model="joinForm.autoConfigureDockerRegistry">允许脚本在 Registry 网络验证通过后配置 Docker HTTP 私有仓库并重启 Docker</el-checkbox>
        <div class="field-hint">默认关闭。只有目标节点尚未配置 HTTP Registry 且确认可以重启 Docker 时再授权。</div>
        <el-collapse class="advanced-box">
          <el-collapse-item title="高级设置" name="advanced">
            <el-row :gutter="16">
              <el-col :span="12"><el-form-item label="节点编号"><el-input v-model="joinForm.serverCode" /></el-form-item></el-col>
              <el-col :span="12"><el-form-item label="节点服务编号"><el-input v-model="joinForm.agentCode" /></el-form-item></el-col>
            </el-row>
          </el-collapse-item>
        </el-collapse>
      </el-form>

      <div v-if="addressWarning" class="warning-card">{{ addressWarning }}</div>

      <div v-if="joinResult" ref="installPanelRef" class="install-panel">
        <div class="install-header">
          <div>
            <div class="install-title">接入命令已生成</div>
            <div class="muted">该命令包含一次性接入凭证，请只发送给可信运维人员。凭证使用后会自动失效。</div>
          </div>
          <el-tag type="success" effect="light">有效期：{{ formatTime(joinResult.expiresAt) }}</el-tag>
        </div>
        <div class="command-block">
          <div class="command-title"><span>第一步：在目标节点执行完整预检</span><el-button size="small" @click="copyText(joinResult.nodeVerificationScript || joinResult.connectivityCommand || '')">复制</el-button></div>
          <pre>{{ joinResult.nodeVerificationScript || joinResult.connectivityCommand }}</pre>
        </div>
        <div class="command-block">
          <div class="command-title"><span>第二步：安装并接入节点</span><el-button size="small" type="primary" @click="copyText(joinResult.installCommand)">复制</el-button></div>
          <pre>{{ joinResult.installCommand }}</pre>
        </div>
      </div>

      <template #footer>
        <el-button @click="onboardingVisible = false">关闭</el-button>
        <el-button type="primary" :disabled="!!addressWarning" @click="createJoin">生成接入命令</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="dialogVisible" title="新增执行节点" width="520px">
      <el-form label-position="top">
        <el-form-item label="公司"><el-select v-if="sessionState.user?.isSuperAdmin" v-model="form.companyId"><el-option v-for="company in companies" :key="company.companyId" :label="company.companyName" :value="company.companyId" /></el-select><el-input v-else :model-value="currentCompanyName" disabled /></el-form-item>
        <el-form-item label="节点标识"><el-input v-model="form.serverCode" /></el-form-item>
        <el-form-item label="节点名称"><el-input v-model="form.serverName" /></el-form-item>
        <el-form-item label="节点地址"><el-input v-model="form.serverIp" /></el-form-item>
        <el-form-item label="同时运行任务上限"><el-input-number v-model="form.maxContainerSlots" :min="1" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createAgentJoinToken, createServer, deleteAgentJoinToken, deleteServer, getSystemSettings, listAgentJoinTokens, listCompanies, listServers } from '../api/platform'
import { sessionState } from '../stores/session'
import { useRoute, useRouter } from 'vue-router'
import type { AgentJoinTokenResult, Company, ControlPlanePreflight, ServerNode } from '../types/api'
import { formatTime, zh } from '../utils/dictionaries'

const route = useRoute()
const router = useRouter()
const rows = ref<ServerNode[]>([])
const loading = ref(false)
const joinInvitations = ref<Array<Record<string, any>>>([])
const companies = ref<Company[]>([])
const dialogVisible = ref(false)
const onboardingVisible = ref(false)
const joinResult = ref<AgentJoinTokenResult | null>(null)
const installPanelRef = ref<HTMLElement | null>(null)
const joinOnlineNotified = ref(false)
let joinPollingTimer: number | undefined
let serverPollingTimer: number | undefined
const joinForm = reactive({ companyId: 0, serverCode: '', serverName: '', agentCode: '', agentName: '', maxContainerSlots: 2, workDir: '/var/lib/crawler-agent', installTarget: 'REMOTE' as 'LOCAL' | 'REMOTE', controlPlaneUrl: '', replaceExistingAgent: true, autoConfigureDockerRegistry: false })
const form = reactive({ companyId: 0, serverCode: '', serverName: '', serverIp: '', maxContainerSlots: 4 })
const currentCompanyName = computed(() => companies.value.find((item) => item.companyId === (sessionState.user?.companyId || form.companyId))?.companyName || '归属公司')
const onboardingJoinedNode = computed(() => rows.value.find((item) => item.serverCode === joinForm.serverCode))
const onboardingNodeOnline = computed(() => Boolean(onboardingJoinedNode.value && onboardingJoinedNode.value.agentConnectionStatus === 'ONLINE'))
const onboardingStepActive = computed(() => onboardingNodeOnline.value ? 3 : (joinResult.value ? 2 : 1))

function hasRuntimeMetrics(row: ServerNode) { return Boolean(row.agentLastHeartbeatAt || row.metrics?.lastHeartbeatAt) }
function serverAddressText(row: ServerNode) { return row.serverIp || row.metrics?.reportedAddress || row.metrics?.hostIp || row.metrics?.publicIp || row.metrics?.hostname || '-' }
function metricText(value?: number | null) { return value === null || value === undefined || Number.isNaN(Number(value)) ? '-' : `${Math.round(Number(value))}%` }
function invitationFor(row: ServerNode) { return joinInvitations.value.find((item) => String(item.server_code || item.serverCode || '') === row.serverCode) }
function nodeStatusText(row: ServerNode) {
  if (row.lifecycleStatus === 'DRAINING') return '维护中'
  if (row.lifecycleStatus === 'DECOMMISSIONING' || row.desiredState === 'DECOMMISSIONED') return '移除中'
  if (row.lifecycleStatus === 'UPGRADING') return '升级中'
  if (row.metrics?.decommissionStatus === 'PENDING') return '移除中'
  if (row.metrics?.decommissionStatus === 'FAILED') return '移除失败'
  if (row.agentConnectionStatus === 'ONLINE') return '在线'
  if (row.agentConnectionStatus === 'OFFLINE') return '离线'
  const invitation = invitationFor(row)
  const status = String(invitation?.invitation_status || invitation?.invitationStatus || '')
  if (status === 'CONFIG_ISSUED') return '接入中'
  if (status === 'FAILED') return '接入失败'
  return '待接入'
}
function nodeStatusTag(row: ServerNode) { const text = nodeStatusText(row); if (text === '在线') return 'success'; if (['离线', '接入失败', '移除失败', '版本不兼容'].includes(text)) return 'danger'; return 'info' }
function nodeStatusHint(row: ServerNode) { const text = nodeStatusText(row); if (text === '接入中') return '容器启动后会立即心跳，默认每 10 秒一次；超过 30 秒请查看 Agent 日志'; if (text === '维护中') return '停止接新任务，等待当前任务结束'; if (text === '移除中') return '等待 Drain/退役收敛'; if (text === '升级中') return '等待 Agent 稳定上线'; return row.lifecycleError || '' }
function invitationStatusText(row: Record<string, any>) { const status = String(row.invitation_status || row.invitationStatus || ''); return ({ PENDING: '待接入', CONFIG_ISSUED: '接入中', FAILED: '接入失败' } as Record<string, string>)[status] || zh(status) }
function invitationResultText(row: Record<string, any>) { return String(row.failure_reason || row.failureReason || row.failure_stage || row.failureStage || '-') }
function canCleanupInvitation(row: Record<string, any>) { const code = String(row.server_code || row.serverCode || ''); return !rows.value.some((item) => item.serverCode === code) }
function preflightTag(status: string) { if (status === 'PASS') return 'success'; if (status === 'FAIL') return 'danger'; if (status === 'PENDING') return 'info'; return 'warning' }
function preflightLabel(status: string) { if (status === 'PASS') return '正常'; if (status === 'FAIL') return '已确认异常'; if (status === 'PENDING') return '待场景验证'; return '运行提醒' }
function goDashboardPreflight() { router.push('/dashboard?focus=platformPreflight') }
function isLoopbackUrl(value: string) { try { const host = new URL(value).hostname.toLowerCase(); return ['127.0.0.1', 'localhost', '0.0.0.0', '::1'].includes(host) } catch { return false } }
const configuredControlPlaneUrl = ref('')
const controlPreflight = ref<ControlPlanePreflight | null>(null)
async function loadSystemSettings() { const data = await getSystemSettings().catch(() => null); configuredControlPlaneUrl.value = data?.controlPlanePublicBaseUrl || ''; controlPreflight.value = data?.controlPlanePreflight || null }
function normalizedCurrentOrigin() { return window.location.origin.replace(/\/+$/, '') }
function resolveControlBaseUrl(value?: string) {
  const configured = (value || '').trim().replace(/\/+$/, '')
  const current = normalizedCurrentOrigin()
  if (!configured) return current
  try {
    const configuredUrl = new URL(configured)
    const currentUrl = new URL(current)
    const sameHost = configuredUrl.protocol === currentUrl.protocol && configuredUrl.hostname === currentUrl.hostname
    const currentHasExplicitPort = Boolean(currentUrl.port)
    if (sameHost && !configuredUrl.port && currentHasExplicitPort) return current
  } catch {
    return configured
  }
  return configured
}
function currentOrigin() { return resolveControlBaseUrl(configuredControlPlaneUrl.value) }
function slug(value: string) { return (value || 'server').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40) || 'server' }
const addressWarning = computed(() => {
  const baseUrl = currentOrigin()
  if (!baseUrl) return '节点连接地址未配置，请超级管理员先到系统设置保存。'
  try { new URL(baseUrl) } catch { return '节点连接地址格式不正确，请到系统设置修正。' }
  if (joinForm.installTarget === 'REMOTE' && isLoopbackUrl(baseUrl)) return '远程节点不能使用本机地址，请到系统设置改成节点可访问的地址。'
  if (joinForm.installTarget === 'REMOTE' && controlPreflight.value && !controlPreflight.value.readyForRemoteAgent) return controlPreflight.value.summary || '平台自检未通过，请先修复必须处理项。'
  return ''
})
function applyAutoCodes() {
  const base = slug(joinForm.serverName || 'test-server')
  if (!joinForm.serverCode) joinForm.serverCode = base
  if (!joinForm.agentCode) joinForm.agentCode = `${base}-executor`
}
function applyInstallTarget() {
  joinForm.controlPlaneUrl = currentOrigin()
  joinForm.workDir = '/var/lib/crawler-agent'
}
function openOnboarding() {
  stopJoinPolling()
  joinResult.value = null
  joinOnlineNotified.value = false
  joinForm.replaceExistingAgent = true
  joinForm.autoConfigureDockerRegistry = false
  onboardingVisible.value = true
  if (!joinForm.companyId) joinForm.companyId = form.companyId
  if (!joinForm.serverName) joinForm.serverName = '上海执行节点01'
  applyAutoCodes()
  applyInstallTarget()
}
function rejoinNode(row: ServerNode) {
  stopJoinPolling()
  joinResult.value = null
  joinOnlineNotified.value = false
  joinForm.companyId = row.companyId
  joinForm.serverCode = row.serverCode
  joinForm.serverName = row.serverName
  joinForm.agentCode = row.agentCode || `${row.serverCode}-executor`
  joinForm.agentName = row.agentName || row.serverName
  joinForm.maxContainerSlots = row.maxContainerSlots || 2
  joinForm.workDir = row.workDir || '/var/lib/crawler-agent'
  joinForm.installTarget = 'REMOTE'
  joinForm.replaceExistingAgent = true
  joinForm.autoConfigureDockerRegistry = false
  applyInstallTarget()
  onboardingVisible.value = true
}
function canRejoinNode(row: ServerNode) { return row.agentConnectionStatus !== 'ONLINE' }
async function cleanupNode(row: ServerNode) {
  try {
    await ElMessageBox.confirm(`确认移除执行节点 ${row.serverName}？在线节点会先自动退役远端 Agent；离线节点会立即失效旧 Token 并清理平台记录。`, '移除执行节点', { type: 'warning', confirmButtonText: '确认移除', cancelButtonText: '取消' })
  } catch {
    return
  }
  const result = await deleteServer(row.serverId)
  if (result.decommissioning) {
    ElMessage.success(result.message || '已下发 Agent 退役指令，确认后节点会自动移除')
  } else {
    ElMessage.success('节点及接入记录已移除')
    if (result.manualCleanupCommand) {
      await ElMessageBox.alert(`平台已使旧 Agent Token 失效。若目标机仍残留 crawler-agent，请在目标机执行：\n\n${result.manualCleanupCommand}`, '远端残留检查', { confirmButtonText: '知道了' })
    }
  }
  await load()
}
async function cleanupInvitation(row: Record<string, any>) {
  const tokenId = Number(row.token_id || row.tokenId || 0)
  if (!tokenId) return
  try {
    await ElMessageBox.confirm(`确认移除“${row.server_name || row.serverName || '该节点'}”的接入记录？`, '清理接入记录', { type: 'warning', confirmButtonText: '确认移除', cancelButtonText: '取消' })
  } catch {
    return
  }
  await deleteAgentJoinToken(tokenId)
  ElMessage.success('接入记录已清理')
  await load()
}
function hasPendingOnboarding() {
  const invitationPending = joinInvitations.value.some((item) => ['PENDING', 'CONFIG_ISSUED'].includes(String(item.invitation_status || item.invitationStatus || '')))
  const nodePending = rows.value.some((item) => ['待接入', '接入中'].includes(nodeStatusText(item)))
  return invitationPending || nodePending
}
function stopServerPolling() {
  if (serverPollingTimer) {
    window.clearInterval(serverPollingTimer)
    serverPollingTimer = undefined
  }
}
function ensureServerPolling() {
  if (hasPendingOnboarding()) {
    if (!serverPollingTimer) serverPollingTimer = window.setInterval(() => { void load(true) }, 10000)
  } else {
    stopServerPolling()
  }
}
async function load(silent = false) {
  if (loading.value) return
  loading.value = !silent
  try {
    await loadSystemSettings()
    companies.value = await listCompanies()
    if (!form.companyId) form.companyId = sessionState.user?.companyId || companies.value[0]?.companyId || 0
    if (!joinForm.companyId) joinForm.companyId = form.companyId
    rows.value = await listServers(sessionState.user?.isSuperAdmin ? undefined : sessionState.user?.companyId || undefined)
    joinInvitations.value = await listAgentJoinTokens(sessionState.user?.isSuperAdmin ? undefined : sessionState.user?.companyId || undefined)
  } finally {
    loading.value = false
    ensureServerPolling()
  }
}
async function refreshPage() {
  await load()
  ElMessage.success('已刷新')
}
async function scrollInstallPanel() {
  await nextTick()
  installPanelRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
function stopJoinPolling() {
  if (joinPollingTimer) {
    window.clearInterval(joinPollingTimer)
    joinPollingTimer = undefined
  }
}
function startJoinPolling() {
  stopJoinPolling()
  joinPollingTimer = window.setInterval(async () => {
    if (!onboardingVisible.value || !joinResult.value) { stopJoinPolling(); return }
    await load(true)
    if (onboardingNodeOnline.value) {
      if (!joinOnlineNotified.value) {
        joinOnlineNotified.value = true
        ElMessage.success('节点已上线')
      }
      stopJoinPolling()
    }
  }, 5000)
}
async function createJoin() {
  if (addressWarning.value) { ElMessage.warning(addressWarning.value); return }
  applyAutoCodes()
  joinOnlineNotified.value = false
  joinResult.value = await createAgentJoinToken({ ...joinForm, controlPlaneUrl: currentOrigin(), agentName: joinForm.agentName || joinForm.serverName, labels: {}, capabilities: {} })
  configuredControlPlaneUrl.value = joinResult.value.controlPlaneUrl || configuredControlPlaneUrl.value
  ElMessage.success('接入命令已生成')
  await scrollInstallPanel()
  startJoinPolling()
}
async function copyText(text: string) {
  if (!text) return
  if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text)
  else {
    const el = document.createElement('textarea')
    el.value = text
    document.body.appendChild(el)
    el.select()
    document.execCommand('copy')
    document.body.removeChild(el)
  }
  ElMessage.success('已复制')
}
async function save() { await createServer(form); dialogVisible.value = false; await load() }
onMounted(async () => { await load(); if (route.query.companyId) { joinForm.companyId = Number(route.query.companyId) || joinForm.companyId; form.companyId = joinForm.companyId } if (route.query.openOnboarding === '1') openOnboarding() })
watch(() => route.query.openOnboarding, (value) => { if (value === '1') openOnboarding() })
onUnmounted(() => { stopJoinPolling(); stopServerPolling() })
</script>
<style scoped>
.server-name { font-weight: 700; color: #111827; }
.hero-toolbar { align-items: flex-start; }
.hero-toolbar h3 { margin: 0 0 6px; }
.node-hint { margin-top: 4px; }
.wizard-steps { margin-bottom: 16px; }
.guide-alert { margin-bottom: 16px; }
.onboarding-form { margin-top: 6px; }
.field-hint { color: #6b7280; font-size: 12px; margin-top: 6px; line-height: 1.5; }
.advanced-box { margin-top: 4px; border-radius: 10px; overflow: hidden; }
.warning-card { margin-top: 12px; padding: 10px 12px; border-radius: 10px; background: #fff7ed; color: #c2410c; border: 1px solid #fed7aa; }
.install-panel { margin-top: 16px; border: 1px solid #dbeafe; background: #eff6ff; border-radius: 14px; padding: 14px; }
.install-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.install-title { font-weight: 800; color: #0f172a; margin-bottom: 4px; }
.command-block { margin-top: 12px; }
.command-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; font-weight: 700; color: #1f2937; }
.command-block pre { white-space: pre-wrap; word-break: break-all; background: #111827; color: #e5e7eb; padding: 12px; border-radius: 10px; margin: 0; }

.preflight-panel { margin: 14px 0; padding: 14px; border-radius: 14px; border: 1px solid #dbeafe; background: #eff6ff; }
.preflight-fail { border-color: #fecaca; background: #fef2f2; }
.preflight-warn { border-color: #fed7aa; background: #fff7ed; }
.preflight-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.preflight-title { font-weight: 800; color: #0f172a; margin-bottom: 4px; }
.port-list { display: grid; gap: 6px; margin: 8px 0 12px; }
.port-item { font-size: 12px; color: #334155; }
.port-item span { display: block; color: #64748b; margin-top: 2px; }
.preflight-checks { display: grid; gap: 8px; }
.preflight-check { display: grid; grid-template-columns: 54px 1fr; gap: 8px; align-items: flex-start; }
.check-label { font-weight: 700; color: #1f2937; margin-bottom: 2px; }
.check-suggestion { margin-top: 4px; color: #b45309; font-size: 12px; }

.join-invitations-card { margin-top: 18px; padding-top: 16px; border-top: 1px solid var(--el-border-color-light); }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.section-header h4 { margin: 0; }
</style>

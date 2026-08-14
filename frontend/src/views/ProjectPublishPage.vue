<template>
  <div class="publish-page" :class="{ 'assistant-open': assistantPanelVisible }">
    <main class="publish-main">
      <div class="page-card form-card">
        <div class="card-header compact-header">
          <div>
            <div class="card-title">发布信息</div>
            <div class="muted">填写发布所需的公司、部署节点、代码仓库和分支。</div>
          </div>
        </div>

        <el-form label-position="left" label-width="112px" class="publish-form">
          <el-form-item label="所属公司">
            <div class="inline-control">
              <el-select v-if="sessionState.user?.isSuperAdmin" v-model="form.companyId" placeholder="选择项目所属公司" filterable class="full-width" @change="onCompanyChanged">
                <el-option v-for="company in companies" :key="company.companyId" :label="company.companyName" :value="company.companyId" />
              </el-select>
              <el-input v-else :model-value="currentCompanyName" disabled class="full-width" />
              <el-button v-if="sessionState.user?.isSuperAdmin" class="append-action" @click="companyDialogVisible = true">新增公司</el-button>
            </div>
          </el-form-item>

          <el-form-item label="部署节点">
            <div class="field-stack">
              <div class="inline-control">
                <el-select v-model="form.serverIds" placeholder="选择当前公司下可部署节点，可多选" multiple collapse-tags collapse-tags-tooltip filterable class="full-width" :disabled="!form.companyId" @change="syncSelectedServerCards">
                  <el-option v-for="server in companyServers" :key="server.serverId" :label="server.serverName" :value="server.serverId" :disabled="!serverDeployable(server)">
                    <div class="server-option">
                      <span>{{ server.serverName }}</span>
                      <span :class="serverDeployable(server) ? 'success' : 'danger'">{{ serverDeployable(server) ? '可部署' : serverBlockReason(server) }}</span>
                    </div>
                  </el-option>
                </el-select>
                <el-button class="append-action" :disabled="!form.companyId" @click="openServerOnboarding">新增节点</el-button>
              </div>
              <div v-if="!form.companyId" class="field-hint">请先选择公司。</div>
              <div v-else-if="companyServers.length === 0" class="field-hint">当前公司暂无执行节点，可在本页新增。</div>
              <div v-if="selectedServerCards.length" class="selected-servers-inline">
                <div v-for="server in selectedServerCards" :key="server.serverId" class="selected-server-pill">
                  <span class="server-name">{{ server.serverName }}</span>
                  <span class="muted">{{ server.serverIp || '未上报地址' }}</span>
                  <el-tag size="small" :type="serverDeployable(server) ? 'success' : 'danger'" effect="light">{{ serverDeployable(server) ? '可部署' : '不可用' }}</el-tag>
                </div>
              </div>
            </div>
          </el-form-item>

          <el-form-item label="Git 仓库地址">
            <div class="field-stack">
              <el-input v-model="form.repositoryUrl" placeholder="例如：https://github.com/zhq910513/baidu_aicaigou.git" @blur="validateRepository" />
              <div class="field-hint">优先匹配已登记项目版本；平台构建能力启用后，将由系统读取代码并构建。</div>
            </div>
          </el-form-item>

          <el-form-item label="分支或标签">
            <el-input v-model="form.refName" placeholder="main" />
          </el-form-item>
        </el-form>

        <div class="publish-actions">
          <el-button :disabled="publishing" @click="resetForm">重置</el-button>
          <el-button :loading="publishing" @click="inspectPipeline">检查流水线</el-button>
          <el-button type="primary" :loading="publishing" @click="publishProject">发布项目</el-button>
        </div>
      </div>
    </main>

    <aside v-if="assistantPanelVisible" class="publish-assistant-panel" :class="{ 'is-collapsing': assistantMode === 'collapsing' }">
      <div class="assistant-header">
        <div>
          <div class="assistant-title">发布助手</div>
          <div class="assistant-subtitle">{{ assistantStatusText }} · {{ assistantProgressPercent }}%</div>
        </div>
        <div class="assistant-actions">
          <el-button size="small" text @click="collapseAssistant">收起</el-button>
          <el-button v-if="publishSucceeded" size="small" text @click="assistantMode = 'closed'">关闭</el-button>
        </div>
      </div>

      <div class="assistant-progress">
        <div v-for="(step, index) in assistantSteps" :key="step.key" class="assistant-step" :class="step.status">
          <span class="step-index">{{ index + 1 }}</span>
          <div>
            <div class="step-title">{{ step.title }}</div>
            <div class="step-message">{{ step.message }}</div>
          </div>
        </div>
      </div>
      <el-alert v-if="publishSummary" class="result-alert" :type="publishSucceeded ? 'success' : 'warning'" :title="publishSummary" show-icon :closable="false" />
      <div v-if="publishTargets.length" class="target-list">
        <div v-for="target in publishTargets" :key="String(target.targetId || target.serverId)" class="target-card">
          <div>
            <div class="server-name">{{ target.serverName || '执行节点' }}</div>
            <div class="muted">{{ target.message || target.targetStatus || '等待节点执行部署指令' }}</div>
          </div>
          <el-tag effect="light">{{ zh(String(target.imageReadinessStatus || target.targetStatus || 'PENDING')) }}</el-tag>
        </div>
      </div>
      <div v-if="publishSucceeded" class="next-actions">
        <el-button type="primary" @click="router.push('/tasks')">进入任务编排</el-button>
        <el-button @click="router.push('/runs')">查看执行记录</el-button>
        <el-button @click="router.push('/projects')">查看项目版本</el-button>
      </div>
    </aside>

    <button
      v-if="assistantMode === 'dock'"
      class="assistant-dock"
      :class="[`is-${assistantState}`, { 'is-dragging': floatDrag.active, 'is-left': floatSide === 'left', 'is-right': floatSide === 'right' }]"
      :style="floatStyle"
      type="button"
      aria-label="展开发布助手"
      @mousedown.prevent="startFloatDrag"
      @click="restoreAssistant"
    >
      <span class="dock-orb" :style="dockProgressStyle"><span class="dock-orb-core">助</span></span>
      <span class="dock-copy">
        <span class="dock-title">发布助手</span>
        <span class="dock-subtitle">{{ assistantStatusText }} · {{ assistantProgressPercent }}%</span>
      </span>
      <span class="dock-pulse" />
    </button>

    <el-dialog v-model="companyDialogVisible" title="新增公司" width="460px">
      <el-form label-position="top">
        <el-form-item label="公司编码"><el-input v-model="companyForm.companyCode" placeholder="例如：ulike" /></el-form-item>
        <el-form-item label="公司名称"><el-input v-model="companyForm.companyName" placeholder="例如：Ulike" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="companyForm.description" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="companyDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="createCompanyInline">保存并选中</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="serverDrawerVisible" title="新增执行节点" size="540px">
      <el-steps :active="joinResult ? 2 : 1" simple class="drawer-steps">
        <el-step title="填写信息" />
        <el-step title="复制命令" />
        <el-step title="等待上线" />
      </el-steps>
      <el-alert class="guide-alert" type="info" show-icon :closable="false" title="连接地址由系统设置统一管理，这里只需要填写节点基础信息。" />
      <div v-if="controlPreflight" class="preflight-panel" :class="`preflight-${controlPreflight.status.toLowerCase()}`">
        <div class="preflight-header">
          <div>
            <div class="preflight-title">接入前检查</div>
            <div class="muted">平台自检：必须处理 {{ controlPreflight.blockingCount }}，需确认 {{ controlPreflight.warningCount }}。完整详情放在运行总览。</div>
          </div>
          <el-tag :type="preflightTag(controlPreflight.status)" effect="light">{{ preflightLabel(controlPreflight.status) }}</el-tag>
        </div>
        <div v-if="controlPreflight.nextAction" class="check-suggestion">下一步：{{ controlPreflight.nextAction }}</div>
        <el-button size="small" @click="router.push('/dashboard?focus=platformPreflight')">查看运行总览平台自检</el-button>
      </div>
      <el-form label-position="top" class="drawer-form">
        <el-form-item label="所属公司"><el-input :model-value="selectedCompanyName" disabled /></el-form-item>
        <el-form-item label="节点名称"><el-input v-model="joinForm.serverName" placeholder="例如：上海执行节点01" @blur="applyJoinCodes" /></el-form-item>
        <el-form-item label="同时运行任务上限"><el-input-number v-model="joinForm.maxContainerSlots" :min="1" :max="100" /></el-form-item>
        <el-form-item label="工作目录"><el-input v-model="joinForm.workDir" /></el-form-item>
      </el-form>
      <el-alert v-if="joinWarning" type="warning" show-icon :closable="false" :title="joinWarning" />
      <div v-if="joinResult" class="install-panel">
        <div class="install-title">接入命令已生成</div>
        <div class="muted">请在目标节点执行下面命令，节点上线后会自动出现在本页下拉列表。</div>
        <div class="command-block">
          <div class="command-title"><span>连通性验证</span><el-button size="small" @click="copyText(joinResult.connectivityCommand || '')">复制</el-button></div>
          <pre>{{ joinResult.connectivityCommand }}</pre>
        </div>
        <div class="command-block">
          <div class="command-title"><span>安装并接入</span><el-button size="small" type="primary" @click="copyText(joinResult.installCommand)">复制</el-button></div>
          <pre>{{ joinResult.installCommand }}</pre>
        </div>
      </div>
      <template #footer>
        <el-button @click="serverDrawerVisible = false">关闭</el-button>
        <el-button type="primary" :disabled="!!joinWarning" @click="createJoinCommand">生成接入命令</el-button>
        <el-button @click="refreshServersAfterJoin">刷新节点</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { apiErrorData } from '../api/client'
import { analyzeProjectPublishPipeline, createAgentJoinToken, createCompany, listCompanies, listServers, getSystemSettings, runProjectPublishPipeline } from '../api/platform'
import { sessionState } from '../stores/session'
import type { AgentJoinTokenResult, Company, ControlPlanePreflight, ProjectPublishPipelineStep, ServerNode } from '../types/api'
import { zh } from '../utils/dictionaries'

const router = useRouter()
const companies = ref<Company[]>([])
const companyServers = ref<ServerNode[]>([])
const selectedServerCards = ref<ServerNode[]>([])
const companyDialogVisible = ref(false)
const serverDrawerVisible = ref(false)
const publishing = ref(false)
const joinResult = ref<AgentJoinTokenResult | null>(null)
const controlBaseUrl = ref('')
const controlPreflight = ref<ControlPlanePreflight | null>(null)
const publishSummary = ref('')
const publishSucceeded = ref(false)
const publishTargets = ref<Array<Record<string, unknown>>>([])
const publishBlockers = ref<Array<Record<string, unknown>>>([])
const pipelineChecked = ref(false)
const pendingJoinServerCode = ref('')
const assistantMode = ref<'panel' | 'collapsing' | 'dock' | 'closed'>('panel')
const floatPosition = reactive({ x: 0, y: 220 })
const floatDrag = reactive({ active: false, moved: false, dx: 0, dy: 0 })
const floatSide = ref<'left' | 'right'>('right')
let collapseTimer: number | undefined
let floatMoveHandler: ((event: MouseEvent) => void) | undefined
let floatUpHandler: (() => void) | undefined

const defaultPublishSteps: ProjectPublishPipelineStep[] = [
  { key: 'company', title: '选择公司', message: '等待检查', status: 'wait' },
  { key: 'servers', title: '选择节点', message: '等待检查', status: 'wait' },
  { key: 'source', title: '确认代码仓库', message: '等待检查', status: 'wait' },
  { key: 'build', title: '构建镜像', message: '等待检查', status: 'wait' },
  { key: 'release', title: '确认可发布版本', message: '等待检查', status: 'wait' },
  { key: 'deploy', title: '部署节点', message: '等待检查', status: 'wait' },
  { key: 'ready', title: '运行前自检', message: '等待检查', status: 'wait' },
]
const publishSteps = ref<ProjectPublishPipelineStep[]>(defaultPublishSteps.map((item) => ({ ...item })))

const form = reactive({ companyId: 0, serverIds: [] as number[], repositoryUrl: '', refName: 'main' })
const companyForm = reactive({ companyCode: '', companyName: '', description: '' })
const joinForm = reactive({ companyId: 0, serverCode: '', serverName: '新执行节点', agentCode: '', agentName: '', maxContainerSlots: 2, workDir: '/var/lib/crawler-agent', installTarget: 'REMOTE' as 'LOCAL' | 'REMOTE', controlPlaneUrl: '' })

const selectedCompanyName = computed(() => companies.value.find((item) => item.companyId === form.companyId)?.companyName || '当前公司')
const currentCompanyName = computed(() => companies.value.find((item) => item.companyId === sessionState.user?.companyId)?.companyName || '归属公司')
const repositoryOk = computed(() => isRepositoryUrl(form.repositoryUrl))
const deployableServers = computed(() => companyServers.value.filter(serverDeployable))
const assistantPanelVisible = computed(() => assistantMode.value === 'panel' || assistantMode.value === 'collapsing')
const assistantSteps = computed<ProjectPublishPipelineStep[]>(() => {
  if (pipelineChecked.value) return mergePipelineStepsWithBlockers(publishSteps.value)
  const next = defaultPublishSteps.map((item) => ({ ...item }))
  const selectedServersReady = form.serverIds.length > 0
  const localReady = Boolean(form.companyId && selectedServersReady && repositoryOk.value && deployableServers.value.length)
  setAssistantStep(next, 'company', form.companyId ? 'success' : 'wait', form.companyId ? `已选择：${selectedCompanyName.value}` : '请选择项目所属公司。')
  setAssistantStep(next, 'servers', serverLocalStatus(), serverLocalMessage())
  setAssistantStep(next, 'source', repositoryOk.value ? 'success' : 'wait', repositoryOk.value ? '仓库地址格式已通过本地检查。' : '请输入以 http(s) 或 git@ 开头的仓库地址。')
  const pendingMessage = localReady ? '等待检查流水线。' : '等待前置信息完成。'
  setAssistantStep(next, 'build', 'wait', pendingMessage)
  setAssistantStep(next, 'release', 'wait', pendingMessage)
  setAssistantStep(next, 'deploy', 'wait', pendingMessage)
  setAssistantStep(next, 'ready', localReady ? 'success' : readyLocalStatus(), localReady ? '本地发布信息已完整，可检查流水线。' : readyLocalMessage())
  return next
})
const assistantDoneCount = computed(() => assistantSteps.value.filter((item) => item.status === 'success').length)
const assistantProgressPercent = computed(() => Math.round((assistantDoneCount.value / Math.max(1, assistantSteps.value.length)) * 100))
const assistantState = computed(() => {
  if (publishSucceeded.value) return 'success'
  if (publishBlockers.value.length || assistantSteps.value.some((item) => item.status === 'error')) return 'blocked'
  if (assistantDoneCount.value || assistantSteps.value.some((item) => item.status === 'process')) return 'active'
  return 'idle'
})
const assistantStatusText = computed(() => {
  if (publishSucceeded.value) return '流程完成'
  if (assistantState.value === 'blocked') return '存在阻断'
  if (assistantState.value === 'active') return `${assistantDoneCount.value}/${assistantSteps.value.length} 已就绪`
  return '待检查'
})
const floatStyle = computed(() => ({ left: `${floatPosition.x}px`, top: `${floatPosition.y}px` }))
const dockProgressStyle = computed(() => ({ '--dock-progress': `${assistantProgressPercent.value * 3.6}deg` }))
const joinWarning = computed(() => {
  if (!form.companyId) return '请先选择公司。'
  if (!joinForm.serverName.trim()) return '请填写节点名称。'
  if (!controlBaseUrl.value) return '节点连接地址未配置，请超级管理员先到系统设置保存。'
  try { new URL(controlBaseUrl.value) } catch { return '节点连接地址格式不正确，请到系统设置修正。' }
  if (controlPreflight.value && !controlPreflight.value.readyForRemoteAgent) return controlPreflight.value.summary || '平台自检未通过，请先修复必须处理项。'
  return ''
})

function slug(value: string) { return (value || 'server').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40) || 'server' }
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
function isRepositoryUrl(value: string) { return /^(https?:\/\/[^\s]+|git@[^\s:]+:[^\s]+)(\.git)?$/i.test(value.trim()) }
function serverDeployable(server: ServerNode) { return !serverBlockReason(server) }
function preflightTag(status: string) { if (status === 'PASS') return 'success'; if (status === 'FAIL') return 'danger'; return 'warning' }
function preflightLabel(status: string) { if (status === 'PASS') return '通过'; if (status === 'FAIL') return '必须处理'; return '需确认' }
function serverBlockReason(server: ServerNode) {
  if (server.manageStatus !== 'ENABLED') return '已停用'
  if (!['HEALTHY', 'DEGRADED'].includes(server.healthStatus)) return server.healthStatus === 'OFFLINE' ? '离线' : '健康异常'
  if (!['NORMAL', 'PRESSURE', 'BUSY'].includes(server.capacityStatus)) return '容量不足'
  const dockerStatus = String(server.metrics?.dockerStatus || '').toUpperCase()
  if (dockerStatus && !['OK', 'READY', 'UNKNOWN'].includes(dockerStatus)) return '容器服务异常'
  if (server.metrics?.dockerSockAccessible === false) return '执行权限不可用'
  if (server.metrics?.projectDataRootWritable === false) return '工作目录不可写'
  return ''
}
function setAssistantStep(steps: ProjectPublishPipelineStep[], key: string, status: string, message: string) {
  const target = steps.find((step) => step.key === key)
  if (!target) return
  target.status = status
  target.message = message
}
function serverLocalStatus() {
  if (!form.companyId) return 'wait'
  if (!companyServers.value.length || !deployableServers.value.length) return 'error'
  return form.serverIds.length ? 'success' : 'wait'
}
function serverLocalMessage() {
  if (!form.companyId) return '等待选择公司。'
  if (!companyServers.value.length) return '当前公司暂无执行节点，可在本页新增。'
  if (!deployableServers.value.length) return '当前公司暂无可部署节点。'
  return form.serverIds.length ? `已选择 ${form.serverIds.length} 台节点。` : `当前公司有 ${deployableServers.value.length} 台可部署节点，请选择。`
}
function readyLocalStatus() {
  if (form.companyId && deployableServers.value.length === 0) return 'error'
  return 'wait'
}
function readyLocalMessage() {
  if (!form.companyId) return '等待选择公司。'
  if (!form.serverIds.length) return '等待选择部署节点。'
  if (!repositoryOk.value) return '等待确认代码仓库。'
  if (!deployableServers.value.length) return '当前公司暂无可部署节点。'
  return '等待检查流水线。'
}
function blockerText(blocker: Record<string, unknown>) {
  return String(blocker.message || blocker.title || blocker.step || '存在阻断')
}
function blockerMatchesStep(blocker: Record<string, unknown>, step: ProjectPublishPipelineStep) {
  const key = String(blocker.step || blocker.key || '').toLowerCase()
  const title = String(blocker.title || '')
  return Boolean((key && (key === step.key.toLowerCase() || key.includes(step.key.toLowerCase()))) || (title && (title === step.title || title.includes(step.title))))
}
function mergePipelineStepsWithBlockers(steps: ProjectPublishPipelineStep[]) {
  const next = defaultPublishSteps.map((step) => ({ ...step }))
  steps.forEach((step) => {
    const target = next.find((item) => item.key === step.key)
    if (target) Object.assign(target, step)
    else next.push({ ...step })
  })
  const unmatched: string[] = []
  publishBlockers.value.forEach((blocker) => {
    const target = next.find((step) => blockerMatchesStep(blocker, step))
    if (!target) { unmatched.push(blockerText(blocker)); return }
    target.status = 'error'
    target.message = blockerText(blocker)
  })
  if (unmatched.length) {
    const target = next.find((step) => step.key === 'ready') || next[next.length - 1]
    if (target) {
      target.status = 'error'
      target.message = unmatched.join('；')
    }
  }
  return next
}
function resetSteps() {
  publishSteps.value = defaultPublishSteps.map((item) => ({ ...item }))
  publishSummary.value = ''
  publishSucceeded.value = false
  publishTargets.value = []
  publishBlockers.value = []
  pipelineChecked.value = false
  assistantMode.value = 'panel'
}
async function loadBase() {
  try {
    const settings = await getSystemSettings().catch(() => null)
    controlBaseUrl.value = resolveControlBaseUrl(settings?.controlPlanePublicBaseUrl)
    controlPreflight.value = settings?.controlPlanePreflight || null
    companies.value = await listCompanies()
    if (!form.companyId) form.companyId = sessionState.user?.companyId || companies.value[0]?.companyId || 0
    await refreshCompanyServers()
  } catch (error) {
    const payload = apiErrorData<unknown>(error)
    ElMessage.error(payload?.message || '发布基础信息加载失败')
  }
}
async function refreshCompanyServers() {
  if (!form.companyId) { companyServers.value = []; return }
  companyServers.value = await listServers(form.companyId)
  form.serverIds = form.serverIds.filter((id) => companyServers.value.some((server) => server.serverId === id && serverDeployable(server)))
  syncSelectedServerCards()
}
function syncSelectedServerCards() { selectedServerCards.value = companyServers.value.filter((server) => form.serverIds.includes(server.serverId)) }
async function onCompanyChanged() { form.serverIds = []; await refreshCompanyServers() }
async function createCompanyInline() {
  if (!companyForm.companyCode.trim() || !companyForm.companyName.trim()) { ElMessage.warning('请填写公司编码和公司名称'); return }
  try {
    const company = await createCompany(companyForm)
    companyDialogVisible.value = false
    companies.value = await listCompanies()
    form.companyId = company.companyId
    await refreshCompanyServers()
    ElMessage.success('公司已创建并选中')
  } catch (error) {
    const payload = apiErrorData<unknown>(error)
    ElMessage.error(payload?.message || '公司创建失败')
  }
}
function applyJoinCodes() {
  const base = slug(joinForm.serverName || 'server')
  joinForm.companyId = form.companyId
  joinForm.serverCode = joinForm.serverCode || base
  joinForm.agentCode = joinForm.agentCode || `${base}-executor`
  joinForm.agentName = joinForm.serverName
  joinForm.controlPlaneUrl = controlBaseUrl.value
}
function openServerOnboarding() {
  joinResult.value = null
  joinForm.companyId = form.companyId
  joinForm.serverName = joinForm.serverName || '新执行节点'
  applyJoinCodes()
  serverDrawerVisible.value = true
}
async function createJoinCommand() {
  if (joinWarning.value) { ElMessage.warning(joinWarning.value); return }
  applyJoinCodes()
  try {
    joinResult.value = await createAgentJoinToken({ ...joinForm, controlPlaneUrl: resolveControlBaseUrl(controlBaseUrl.value), labels: {}, capabilities: {} })
    controlBaseUrl.value = joinResult.value.controlPlaneUrl || controlBaseUrl.value
    pendingJoinServerCode.value = joinForm.serverCode
    const warning = joinResult.value.warnings?.[0]
    if (warning) ElMessage.warning(warning)
    else ElMessage.success('接入命令已生成')
  } catch (error) {
    const payload = apiErrorData<unknown>(error)
    ElMessage.error(payload?.message || '接入命令生成失败')
  }
}
async function refreshServersAfterJoin() {
  await refreshCompanyServers()
  const joined = companyServers.value.find((server) => server.serverCode === pendingJoinServerCode.value)
  if (joined && serverDeployable(joined) && !form.serverIds.includes(joined.serverId)) {
    form.serverIds.push(joined.serverId)
    syncSelectedServerCards()
    serverDrawerVisible.value = false
    ElMessage.success('节点已上线并自动选中')
    return
  }
  ElMessage.success('节点列表已刷新')
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
function validateRepository() { if (form.repositoryUrl && !repositoryOk.value) ElMessage.warning('仓库地址格式不正确') }
function validatePublishForm() {
  if (!form.companyId) return '请选择项目所属公司'
  if (!form.serverIds.length) return '请选择至少一个可部署节点'
  if (!repositoryOk.value) return '请填写正确的代码仓库地址'
  const unavailable = selectedServerCards.value.find((server) => !serverDeployable(server))
  if (unavailable) return `节点“${unavailable.serverName}”当前不可部署：${serverBlockReason(unavailable)}`
  return ''
}
function pipelinePayload() {
  return { companyId: form.companyId, serverIds: form.serverIds, repositoryUrl: form.repositoryUrl, refName: form.refName || 'main' }
}
function applyPipelineResult(result: { steps?: ProjectPublishPipelineStep[]; blockers?: Array<Record<string, unknown>>; targets?: Array<Record<string, unknown>>; deployment?: { targets?: Array<Record<string, unknown>> }; message?: string; canContinue?: boolean }) {
  if (result.steps?.length) publishSteps.value = result.steps.map((item) => ({ ...item }))
  publishBlockers.value = result.blockers || []
  publishTargets.value = result.targets || result.deployment?.targets || []
  publishSummary.value = result.message || ''
  publishSucceeded.value = Boolean(result.canContinue && (result.deployment || publishTargets.value.length))
  pipelineChecked.value = true
  assistantMode.value = 'panel'
}
async function inspectPipeline() {
  const problem = validatePublishForm()
  if (problem) { ElMessage.warning(problem); return }
  resetSteps()
  publishing.value = true
  try {
    const result = await analyzeProjectPublishPipeline(pipelinePayload())
    applyPipelineResult(result)
    if (result.canContinue) ElMessage.success('发布流水线前置检查通过')
    else ElMessage.warning(result.message || '发布流水线存在必须处理项')
  } catch (error) {
    const payload = apiErrorData<unknown>(error)
    const message = payload?.message || (error instanceof Error ? error.message : '流水线检查失败')
    publishSummary.value = message
    pipelineChecked.value = true
    assistantMode.value = 'panel'
    ElMessage.error(message)
  } finally {
    publishing.value = false
  }
}
async function publishProject() {
  const problem = validatePublishForm()
  if (problem) { ElMessage.warning(problem); return }
  resetSteps()
  publishing.value = true
  try {
    const analysis = await analyzeProjectPublishPipeline(pipelinePayload())
    applyPipelineResult(analysis)
    if (!analysis.canContinue) {
      ElMessage.warning(analysis.message || '发布流水线存在必须处理项')
      return
    }
    const result = await runProjectPublishPipeline(pipelinePayload())
    applyPipelineResult(result)
    publishSucceeded.value = true
    ElMessage.success('发布流水线已进入节点自检阶段')
  } catch (error) {
    const payload = apiErrorData<unknown>(error)
    const data = payload?.data as { steps?: ProjectPublishPipelineStep[]; blockers?: Array<Record<string, unknown>>; message?: string } | undefined
    if (data?.steps) applyPipelineResult({ ...data, message: payload?.message || data.message })
    const message = payload?.message || (error instanceof Error ? error.message : '发布失败')
    const running = publishSteps.value.find((item) => item.status === 'process')
    if (running) running.status = 'error'
    publishSummary.value = message
    pipelineChecked.value = true
    assistantMode.value = 'panel'
    ElMessage.error(message)
  } finally {
    publishing.value = false
  }
}
function resetForm() {
  form.serverIds = []
  form.repositoryUrl = ''
  form.refName = 'main'
  syncSelectedServerCards()
  resetSteps()
}
function dockBounds() {
  return { minX: 12, maxX: Math.max(12, window.innerWidth - 206), minY: 86, maxY: Math.max(86, window.innerHeight - 92) }
}
function clampDockPosition() {
  const bounds = dockBounds()
  floatPosition.y = Math.min(bounds.maxY, Math.max(bounds.minY, floatPosition.y))
  floatPosition.x = floatSide.value === 'left' ? bounds.minX : bounds.maxX
}
function cleanupFloatDragListeners() {
  if (floatMoveHandler) window.removeEventListener('mousemove', floatMoveHandler)
  if (floatUpHandler) window.removeEventListener('mouseup', floatUpHandler)
  floatMoveHandler = undefined
  floatUpHandler = undefined
}
function collapseAssistant() {
  if (publishSucceeded.value) { assistantMode.value = 'closed'; return }
  if (collapseTimer) window.clearTimeout(collapseTimer)
  floatSide.value = 'right'
  clampDockPosition()
  assistantMode.value = 'collapsing'
  collapseTimer = window.setTimeout(() => {
    clampDockPosition()
    assistantMode.value = 'dock'
  }, 180)
}
function restoreAssistant() {
  if (floatDrag.moved) { floatDrag.moved = false; return }
  assistantMode.value = 'panel'
}
function startFloatDrag(event: MouseEvent) {
  cleanupFloatDragListeners()
  floatDrag.active = true
  floatDrag.moved = false
  floatDrag.dx = event.clientX - floatPosition.x
  floatDrag.dy = event.clientY - floatPosition.y
  floatMoveHandler = (moveEvent: MouseEvent) => {
    if (!floatDrag.active) return
    const bounds = dockBounds()
    const nextX = Math.min(bounds.maxX, Math.max(bounds.minX, moveEvent.clientX - floatDrag.dx))
    const nextY = Math.min(bounds.maxY, Math.max(bounds.minY, moveEvent.clientY - floatDrag.dy))
    if (Math.abs(nextX - floatPosition.x) > 2 || Math.abs(nextY - floatPosition.y) > 2) floatDrag.moved = true
    floatPosition.x = nextX
    floatPosition.y = nextY
  }
  floatUpHandler = () => {
    floatDrag.active = false
    floatSide.value = floatPosition.x < window.innerWidth / 2 ? 'left' : 'right'
    clampDockPosition()
    cleanupFloatDragListeners()
  }
  window.addEventListener('mousemove', floatMoveHandler)
  window.addEventListener('mouseup', floatUpHandler)
}

onMounted(() => {
  clampDockPosition()
  loadBase()
})
onUnmounted(() => {
  if (collapseTimer) window.clearTimeout(collapseTimer)
  cleanupFloatDragListeners()
})
</script>

<style scoped>
.publish-page { position: relative; min-height: calc(100vh - 116px); transition: padding-right 0.18s ease; }
.publish-page.assistant-open { padding-right: 360px; }
.publish-main { width: min(100%, 1180px); }
.form-card { min-height: 100%; }
.compact-header { padding-bottom: 14px; border-bottom: 1px solid #eef2f7; }
.publish-form { margin-top: 18px; }
.publish-form :deep(.el-form-item) { margin-bottom: 20px; align-items: flex-start; }
.publish-form :deep(.el-form-item__label) { height: 38px; line-height: 38px; justify-content: flex-start; color: #334155; font-weight: 800; }
.publish-form :deep(.el-input__wrapper), .publish-form :deep(.el-select__wrapper) { min-height: 38px; }
.field-stack { display: grid; gap: 8px; width: 100%; }
.inline-control { display: flex; gap: 10px; align-items: center; width: 100%; }
.inline-control .full-width { flex: 1; min-width: 0; }
.append-action { width: 104px; flex: 0 0 104px; }
.field-hint { color: #64748b; font-size: 12px; line-height: 1.5; }
.server-option { display: flex; align-items: center; justify-content: space-between; gap: 16px; width: 100%; }
.selected-servers-inline { display: grid; gap: 8px; }
.selected-server-pill { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 9px 10px; border: 1px solid #e7edf5; border-radius: 12px; background: #f8fafc; }
.publish-actions { display: flex; justify-content: flex-end; gap: 8px; padding-top: 16px; margin-top: 2px; border-top: 1px solid #eef2f7; }
.server-name { font-weight: 800; color: #111827; }
.publish-assistant-panel { position: fixed; top: 82px; right: 18px; z-index: 20; width: 328px; max-height: calc(100vh - 104px); overflow-y: auto; padding: 14px; border: 1px solid rgba(203, 213, 225, 0.72); border-radius: 20px; background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.92)); backdrop-filter: blur(16px); box-shadow: 0 22px 54px rgba(15, 23, 42, 0.16); transform-origin: right center; transition: opacity 0.18s ease, transform 0.18s ease, filter 0.18s ease; }
.publish-assistant-panel::before { content: ''; position: absolute; inset: 0; pointer-events: none; border-radius: inherit; background: radial-gradient(circle at 20% 0%, rgba(59, 130, 246, 0.18), transparent 32%), radial-gradient(circle at 92% 18%, rgba(14, 165, 233, 0.13), transparent 36%); }
.publish-assistant-panel.is-collapsing { opacity: 0; transform: translateX(42px) scale(0.9); filter: blur(1px); }
.assistant-header { position: relative; display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; padding-bottom: 12px; border-bottom: 1px solid #eef2f7; }
.assistant-title { font-size: 16px; font-weight: 900; color: #111827; }
.assistant-subtitle { margin-top: 3px; color: #64748b; font-size: 12px; }
.assistant-actions { display: flex; gap: 2px; }
.assistant-progress { display: grid; gap: 9px; margin-top: 13px; }
.assistant-step { display: grid; grid-template-columns: 25px 1fr; gap: 10px; padding: 10px; border: 1px solid #e5eaf2; border-radius: 12px; background: #fff; }
.step-index { display: flex; align-items: center; justify-content: center; width: 24px; height: 24px; border-radius: 999px; background: #e2e8f0; color: #475569; font-size: 12px; font-weight: 800; }
.assistant-step.success { border-color: #bbf7d0; background: #f0fdf4; }
.assistant-step.success .step-index { background: #22c55e; color: #fff; }
.assistant-step.process { border-color: #bfdbfe; background: #eff6ff; }
.assistant-step.process .step-index { background: #2563eb; color: #fff; }
.assistant-step.error { border-color: #fecaca; background: #fff7f7; }
.assistant-step.error .step-index { background: #ef4444; color: #fff; }
.step-title { font-size: 13px; font-weight: 800; color: #111827; }
.step-message { margin-top: 3px; color: #64748b; font-size: 12px; line-height: 1.45; }
.result-alert { margin-top: 12px; }
.target-list { margin-top: 10px; }
.target-card { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 11px 12px; border: 1px solid #e7edf5; border-radius: 12px; background: #fff; margin-top: 10px; }
.next-actions { display: grid; gap: 8px; margin-top: 14px; }
.assistant-dock { position: fixed; z-index: 30; display: grid; grid-template-columns: 46px 1fr 8px; align-items: center; gap: 10px; width: 194px; height: 66px; padding: 9px 12px 9px 10px; border: 1px solid rgba(255, 255, 255, 0.78); border-radius: 999px; color: #0f172a; background: linear-gradient(135deg, rgba(255, 255, 255, 0.92), rgba(239, 246, 255, 0.9)); backdrop-filter: blur(14px); box-shadow: 0 18px 46px rgba(15, 23, 42, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.72); cursor: grab; user-select: none; transition: left 0.22s cubic-bezier(0.2, 0.8, 0.2, 1), top 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease; }
.assistant-dock::before { content: ''; position: absolute; inset: -10px; z-index: -1; border-radius: inherit; opacity: 0.36; background: radial-gradient(circle, rgba(37, 99, 235, 0.32), transparent 62%); animation: dock-breathe 2.4s ease-in-out infinite; }
.assistant-dock.is-left { border-top-left-radius: 16px; border-bottom-left-radius: 16px; }
.assistant-dock.is-right { border-top-right-radius: 16px; border-bottom-right-radius: 16px; }
.assistant-dock:hover { transform: translateY(-1px); box-shadow: 0 22px 54px rgba(15, 23, 42, 0.22), inset 0 1px 0 rgba(255, 255, 255, 0.76); }
.assistant-dock:active, .assistant-dock.is-dragging { cursor: grabbing; transform: scale(0.985); }
.assistant-dock.is-success .dock-orb { color: #16a34a; }
.assistant-dock.is-blocked .dock-orb { color: #ef4444; }
.assistant-dock.is-active .dock-orb { color: #2563eb; }
.assistant-dock.is-idle .dock-orb { color: #64748b; }
.dock-orb { display: grid; place-items: center; width: 46px; height: 46px; border-radius: 999px; background: conic-gradient(currentColor var(--dock-progress), rgba(226, 232, 240, 0.96) 0); box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.76); }
.dock-orb-core { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 999px; background: linear-gradient(135deg, #ffffff, #eff6ff); color: #0f172a; font-weight: 900; font-size: 14px; }
.dock-copy { min-width: 0; display: grid; gap: 3px; text-align: left; }
.dock-title { color: #0f172a; font-size: 13px; font-weight: 900; line-height: 1.1; }
.dock-subtitle { overflow: hidden; color: #64748b; font-size: 12px; line-height: 1.2; text-overflow: ellipsis; white-space: nowrap; }
.dock-pulse { width: 8px; height: 8px; border-radius: 999px; background: #94a3b8; box-shadow: 0 0 0 5px rgba(148, 163, 184, 0.14); }
.assistant-dock.is-active .dock-pulse { background: #2563eb; box-shadow: 0 0 0 5px rgba(37, 99, 235, 0.16); }
.assistant-dock.is-success .dock-pulse { background: #16a34a; box-shadow: 0 0 0 5px rgba(22, 163, 74, 0.15); }
.assistant-dock.is-blocked .dock-pulse { background: #ef4444; box-shadow: 0 0 0 5px rgba(239, 68, 68, 0.15); }
@keyframes dock-breathe { 0%, 100% { opacity: 0.25; transform: scale(0.98); } 50% { opacity: 0.46; transform: scale(1.03); } }
.drawer-steps { margin-bottom: 14px; }
.drawer-form { margin-top: 12px; }
.guide-alert { margin-bottom: 12px; }
.install-panel { margin-top: 14px; border: 1px solid #dbeafe; background: #eff6ff; border-radius: 14px; padding: 14px; }
.install-title { font-weight: 800; margin-bottom: 4px; }
.command-block { margin-top: 12px; }
.command-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; font-weight: 700; color: #1f2937; }
.command-block pre { white-space: pre-wrap; word-break: break-all; background: #111827; color: #e5e7eb; padding: 12px; border-radius: 10px; margin: 0; }
@media (max-width: 1280px) { .publish-page.assistant-open { padding-right: 0; } .publish-assistant-panel { position: static; width: auto; max-height: none; margin-top: 14px; } .publish-main { width: 100%; } }
@media (max-width: 900px) { .assistant-dock { width: 174px; } .publish-form :deep(.el-form-item) { display: block; } .publish-form :deep(.el-form-item__label) { width: auto !important; height: auto; line-height: 1.4; margin-bottom: 6px; } .inline-control { flex-direction: column; align-items: stretch; } .append-action { width: 100%; flex-basis: auto; } .selected-server-pill { align-items: flex-start; flex-direction: column; } }

.preflight-panel { margin: 12px 0; padding: 12px; border-radius: 12px; border: 1px solid #dbeafe; background: #eff6ff; }
.preflight-fail { border-color: #fecaca; background: #fef2f2; }
.preflight-warn { border-color: #fed7aa; background: #fff7ed; }
.preflight-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 8px; }
.preflight-title { font-weight: 800; color: #0f172a; margin-bottom: 4px; }
.port-list { display: grid; gap: 6px; margin-top: 8px; }
.port-item { font-size: 12px; color: #334155; }
.port-item span { display: block; color: #64748b; margin-top: 2px; }
</style>

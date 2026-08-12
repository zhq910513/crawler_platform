<template>
  <div class="publish-page">
    <div class="page-card publish-hero">
      <div>
        <div class="eyebrow">项目交付主入口</div>
        <h2>发布已开发好的爬虫项目</h2>
        <p>选择公司、选择一台或多台服务器、填写代码仓库地址后发布。构建、版本、镜像和部署细节由系统流程承接。</p>
      </div>
      <div class="hero-actions">
        <el-button @click="router.push('/projects')">查看项目版本</el-button>
        <el-button @click="router.push('/tasks')">进入任务编排</el-button>
      </div>
    </div>

    <el-row :gutter="16" class="publish-grid">
      <el-col :xs="24" :lg="14">
        <div class="page-card">
          <div class="card-header">
            <div>
              <div class="card-title">发布信息</div>
              <div class="muted">普通发布只需要填写下面四项，高级构建细节不在这里展开。</div>
            </div>
            <el-tag effect="light">默认发布流程</el-tag>
          </div>
          <el-form label-position="top" class="publish-form">
            <el-form-item label="所属公司">
              <div class="inline-control">
                <el-select v-if="sessionState.user?.isSuperAdmin" v-model="form.companyId" placeholder="选择项目所属公司" filterable class="full-width" @change="onCompanyChanged">
                  <el-option v-for="company in companies" :key="company.companyId" :label="company.companyName" :value="company.companyId" />
                </el-select>
                <el-input v-else :model-value="currentCompanyName" disabled />
                <el-button v-if="sessionState.user?.isSuperAdmin" @click="companyDialogVisible = true">新增公司</el-button>
              </div>
            </el-form-item>

            <el-form-item label="部署服务器">
              <div class="inline-control">
                <el-select v-model="form.serverIds" placeholder="选择当前公司下可部署服务器，可多选" multiple collapse-tags collapse-tags-tooltip filterable class="full-width" :disabled="!form.companyId" @change="syncSelectedServerCards">
                  <el-option v-for="server in companyServers" :key="server.serverId" :label="server.serverName" :value="server.serverId" :disabled="!serverDeployable(server)">
                    <div class="server-option">
                      <span>{{ server.serverName }}</span>
                      <span :class="serverDeployable(server) ? 'success' : 'danger'">{{ serverDeployable(server) ? '可部署' : serverBlockReason(server) }}</span>
                    </div>
                  </el-option>
                </el-select>
                <el-button :disabled="!form.companyId" @click="openServerOnboarding">新增服务器</el-button>
              </div>
              <div v-if="!form.companyId" class="field-hint">请先选择公司。</div>
              <div v-else-if="companyServers.length === 0" class="field-hint">当前公司暂无服务器，可在本页新增。</div>
            </el-form-item>

            <el-form-item label="Git 仓库地址">
              <el-input v-model="form.repositoryUrl" placeholder="例如：https://github.com/zhq910513/baidu_aicaigou.git" @blur="validateRepository" />
              <div class="field-hint">当前版本会优先查找该仓库已登记的项目版本；平台内置构建中心启用后，将由系统直接读取代码并构建。</div>
            </el-form-item>
            <el-form-item label="分支或标签">
              <el-input v-model="form.refName" placeholder="main" />
            </el-form-item>
          </el-form>
          <div class="publish-actions">
            <el-button @click="resetForm">重置</el-button>
            <el-button :loading="publishing" @click="inspectPipeline">检查流水线</el-button>
            <el-button type="primary" :loading="publishing" @click="publishProject">发布项目</el-button>
          </div>
        </div>
      </el-col>

      <el-col :xs="24" :lg="10">
        <div class="page-card">
          <div class="card-title">发布前检查</div>
          <div class="check-list">
            <div v-for="item in checkItems" :key="item.key" class="check-item">
              <el-tag :type="item.ok ? 'success' : 'warning'" effect="light">{{ item.ok ? '已满足' : '待处理' }}</el-tag>
              <div>
                <div class="check-title">{{ item.title }}</div>
                <div class="muted">{{ item.message }}</div>
              </div>
            </div>
          </div>
        </div>

        <div class="page-card selected-servers-card">
          <div class="card-title">已选服务器</div>
          <el-empty v-if="selectedServerCards.length === 0" description="暂未选择服务器" />
          <div v-for="server in selectedServerCards" :key="server.serverId" class="server-card">
            <div>
              <div class="server-name">{{ server.serverName }}</div>
              <div class="muted">{{ server.serverIp || '未上报地址' }}</div>
            </div>
            <el-tag :type="serverDeployable(server) ? 'success' : 'danger'" effect="light">{{ serverDeployable(server) ? '可部署' : '不可用' }}</el-tag>
          </div>
        </div>
      </el-col>
    </el-row>

    <div class="page-card result-card">
      <div class="card-header">
        <div><div class="card-title">发布助手流水线</div><div class="muted">每一步按顺序检查，缺失配置或状态异常会立即卡住，不能跳过继续。</div></div>
        <el-button size="small" @click="clearResult">清空</el-button>
      </div>
      <el-steps :active="activeStep" finish-status="success" process-status="process" align-center>
        <el-step v-for="step in publishSteps" :key="step.key" :title="step.title" :description="step.message" :status="step.status" />
      </el-steps>
      <el-alert v-if="publishSummary" class="result-alert" :type="publishSucceeded ? 'success' : 'warning'" :title="publishSummary" show-icon :closable="false" />
      <div v-if="publishBlockers.length" class="blocker-list">
        <div v-for="blocker in publishBlockers" :key="String(blocker.step || blocker.title)" class="blocker-item">
          <el-tag type="danger" effect="light">阻断</el-tag>
          <div>
            <div class="check-title">{{ blocker.title || blocker.step }}</div>
            <div class="muted">{{ blocker.message }}</div>
          </div>
        </div>
      </div>
      <div v-if="publishTargets.length" class="target-list">
        <div v-for="target in publishTargets" :key="String(target.targetId || target.serverId)" class="target-card">
          <div>
            <div class="server-name">{{ target.serverName || '服务器' }}</div>
            <div class="muted">{{ target.message || target.targetStatus || '等待服务器执行部署指令' }}</div>
          </div>
          <el-tag effect="light">{{ zh(String(target.imageReadinessStatus || target.targetStatus || 'PENDING')) }}</el-tag>
        </div>
      </div>
      <div v-if="publishSucceeded" class="next-actions">
        <el-button type="primary" @click="router.push('/tasks')">进入任务编排</el-button>
        <el-button @click="router.push('/runs')">查看执行记录</el-button>
        <el-button @click="router.push('/projects')">查看项目版本</el-button>
      </div>
    </div>

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

    <el-drawer v-model="serverDrawerVisible" title="新增服务器" size="560px">
      <el-steps :active="joinResult ? 2 : 1" simple class="drawer-steps">
        <el-step title="填写信息" />
        <el-step title="复制命令" />
        <el-step title="等待上线" />
      </el-steps>
      <el-form label-position="top" class="drawer-form">
        <el-form-item label="所属公司"><el-input :model-value="selectedCompanyName" disabled /></el-form-item>
        <el-form-item label="服务器名称"><el-input v-model="joinForm.serverName" placeholder="例如：上海服务器01" @blur="applyJoinCodes" /></el-form-item>
        <el-form-item label="最大并发"><el-input-number v-model="joinForm.maxContainerSlots" :min="1" :max="100" /></el-form-item>
        <el-form-item label="控制端公网回调地址"><el-input v-model="joinForm.controlPlaneUrl" /></el-form-item>
        <el-form-item label="工作目录"><el-input v-model="joinForm.workDir" /></el-form-item>
      </el-form>
      <el-alert v-if="joinWarning" type="warning" show-icon :closable="false" :title="joinWarning" />
      <div v-if="joinResult" class="install-panel">
        <div class="install-title">接入命令已生成</div>
        <div class="muted">请在目标服务器执行下面命令，服务器上线后会自动出现在本页下拉列表。</div>
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
        <el-button @click="refreshServersAfterJoin">刷新服务器</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { apiErrorData } from '../api/client'
import { analyzeProjectPublishPipeline, createAgentJoinToken, createCompany, listCompanies, listServers, getSystemSettings, runProjectPublishPipeline } from '../api/platform'
import { sessionState } from '../stores/session'
import type { AgentJoinTokenResult, Company, ProjectPublishPipelineStep, ServerNode } from '../types/api'
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
const publishSummary = ref('')
const publishSucceeded = ref(false)
const publishTargets = ref<Array<Record<string, unknown>>>([])
const publishBlockers = ref<Array<Record<string, unknown>>>([])
const pendingJoinServerCode = ref('')

const defaultPublishSteps: ProjectPublishPipelineStep[] = [
  { key: 'company', title: '选择公司', message: '等待检查', status: 'wait' },
  { key: 'servers', title: '选择服务器', message: '等待检查', status: 'wait' },
  { key: 'source', title: '确认代码仓库', message: '等待检查', status: 'wait' },
  { key: 'build', title: '构建镜像', message: '等待检查', status: 'wait' },
  { key: 'release', title: '确认可发布版本', message: '等待检查', status: 'wait' },
  { key: 'deploy', title: '部署服务器', message: '等待检查', status: 'wait' },
  { key: 'ready', title: '运行前自检', message: '等待检查', status: 'wait' },
]
const publishSteps = ref<ProjectPublishPipelineStep[]>(defaultPublishSteps.map((item) => ({ ...item })))
const activeStep = computed(() => Math.max(0, publishSteps.value.findIndex((item) => item.status === 'process')))

const form = reactive({ companyId: 0, serverIds: [] as number[], repositoryUrl: '', refName: 'main' })
const companyForm = reactive({ companyCode: '', companyName: '', description: '' })
const joinForm = reactive({ companyId: 0, serverCode: '', serverName: '新服务器', agentCode: '', agentName: '', maxContainerSlots: 2, workDir: '/var/lib/crawler-agent', installTarget: 'REMOTE' as 'LOCAL' | 'REMOTE', controlPlaneUrl: '' })

const selectedCompanyName = computed(() => companies.value.find((item) => item.companyId === form.companyId)?.companyName || '当前公司')
const currentCompanyName = computed(() => companies.value.find((item) => item.companyId === sessionState.user?.companyId)?.companyName || '归属公司')
const repositoryOk = computed(() => isRepositoryUrl(form.repositoryUrl))
const deployableServers = computed(() => companyServers.value.filter(serverDeployable))
const checkItems = computed(() => [
  { key: 'company', title: '公司', ok: Boolean(form.companyId), message: form.companyId ? `已选择：${selectedCompanyName.value}` : '请选择项目所属公司。' },
  { key: 'servers', title: '服务器', ok: form.serverIds.length > 0, message: form.serverIds.length ? `已选择 ${form.serverIds.length} 台服务器。` : '请选择至少一台可部署服务器。' },
  { key: 'repo', title: '代码仓库', ok: repositoryOk.value, message: repositoryOk.value ? '仓库地址格式已通过本地检查。' : '请输入以 http(s) 或 git@ 开头的仓库地址。' },
  { key: 'ready', title: '发布准备', ok: deployableServers.value.length > 0, message: deployableServers.value.length ? `当前公司有 ${deployableServers.value.length} 台可部署服务器。` : '当前公司暂无可部署服务器。' },
])
const joinWarning = computed(() => {
  if (!form.companyId) return '请先选择公司。'
  if (!joinForm.serverName.trim()) return '请填写服务器名称。'
  if (!joinForm.controlPlaneUrl) return '请填写控制端公网回调地址。'
  try { new URL(joinForm.controlPlaneUrl) } catch { return '控制端公网回调地址格式不正确。' }
  return ''
})

function slug(value: string) { return (value || 'server').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40) || 'server' }
function isRepositoryUrl(value: string) { return /^(https?:\/\/[^\s]+|git@[^\s:]+:[^\s]+)(\.git)?$/i.test(value.trim()) }
function serverDeployable(server: ServerNode) { return !serverBlockReason(server) }
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
function resetSteps() {
  publishSteps.value.forEach((step) => { step.status = 'wait'; step.message = '等待发布' })
  publishSummary.value = ''
  publishSucceeded.value = false
  publishTargets.value = []
  publishBlockers.value = []
}
async function loadBase() {
  try {
    const settings = await getSystemSettings().catch(() => null)
    controlBaseUrl.value = settings?.controlPlanePublicBaseUrl || window.location.origin
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
}
function openServerOnboarding() {
  joinResult.value = null
  joinForm.companyId = form.companyId
  joinForm.serverName = joinForm.serverName || '新服务器'
  joinForm.controlPlaneUrl = controlBaseUrl.value || window.location.origin
  applyJoinCodes()
  serverDrawerVisible.value = true
}
async function createJoinCommand() {
  if (joinWarning.value) { ElMessage.warning(joinWarning.value); return }
  applyJoinCodes()
  try {
    joinResult.value = await createAgentJoinToken({ ...joinForm, labels: {}, capabilities: {} })
    pendingJoinServerCode.value = joinForm.serverCode
    ElMessage.success('接入命令已生成')
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
    ElMessage.success('服务器已上线并自动选中')
    return
  }
  ElMessage.success('服务器列表已刷新')
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
  if (!form.serverIds.length) return '请选择至少一台可部署服务器'
  if (!repositoryOk.value) return '请填写正确的代码仓库地址'
  const unavailable = selectedServerCards.value.find((server) => !serverDeployable(server))
  if (unavailable) return `服务器“${unavailable.serverName}”当前不可部署：${serverBlockReason(unavailable)}`
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
    else ElMessage.warning(result.message || '发布流水线存在阻断项')
  } catch (error) {
    const payload = apiErrorData<unknown>(error)
    const message = payload?.message || (error instanceof Error ? error.message : '流水线检查失败')
    publishSummary.value = message
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
      ElMessage.warning(analysis.message || '发布流水线存在阻断项')
      return
    }
    const result = await runProjectPublishPipeline(pipelinePayload())
    applyPipelineResult(result)
    publishSucceeded.value = true
    ElMessage.success('发布流水线已进入服务器自检阶段')
  } catch (error) {
    const payload = apiErrorData<unknown>(error)
    const data = payload?.data as { steps?: ProjectPublishPipelineStep[]; blockers?: Array<Record<string, unknown>>; message?: string } | undefined
    if (data?.steps) applyPipelineResult({ ...data, message: payload?.message || data.message })
    const message = payload?.message || (error instanceof Error ? error.message : '发布失败')
    const running = publishSteps.value.find((item) => item.status === 'process')
    if (running) running.status = 'error'
    publishSummary.value = message
    ElMessage.error(message)
  } finally {
    publishing.value = false
  }
}
function clearResult() { resetSteps() }
function resetForm() {
  form.serverIds = []
  form.repositoryUrl = ''
  form.refName = 'main'
  syncSelectedServerCards()
  resetSteps()
}

onMounted(loadBase)
</script>

<style scoped>
.publish-page { display: grid; gap: 16px; }
.publish-hero { display: flex; align-items: center; justify-content: space-between; gap: 16px; background: linear-gradient(135deg, #eef6ff, #ffffff); }
.publish-hero h2 { margin: 6px 0; font-size: 24px; }
.publish-hero p { margin: 0; color: #64748b; line-height: 1.6; }
.eyebrow { color: #2563eb; font-weight: 800; font-size: 12px; letter-spacing: 0.08em; }
.hero-actions { display: flex; gap: 8px; }
.publish-grid { align-items: stretch; }
.publish-form { margin-top: 18px; }
.inline-control { display: flex; gap: 10px; align-items: center; width: 100%; }
.inline-control .full-width { flex: 1; }
.field-hint { margin-top: 6px; color: #64748b; font-size: 12px; line-height: 1.5; }
.server-option { display: flex; align-items: center; justify-content: space-between; gap: 16px; width: 100%; }
.publish-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 10px; }
.check-list { display: grid; gap: 12px; margin-top: 16px; }
.check-item { display: grid; grid-template-columns: 70px 1fr; gap: 12px; align-items: flex-start; padding: 12px; border: 1px solid #e7edf5; border-radius: 12px; background: #f8fafc; }
.check-title { font-weight: 800; color: #111827; }
.selected-servers-card { margin-top: 16px; }
.server-card, .target-card { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px; border: 1px solid #e7edf5; border-radius: 12px; background: #fff; margin-top: 10px; }
.server-name { font-weight: 800; color: #111827; }
.result-card { overflow: hidden; }
.result-alert { margin-top: 18px; }
.blocker-list { display: grid; gap: 10px; margin-top: 16px; }
.blocker-item { display: flex; align-items: flex-start; gap: 10px; padding: 10px 12px; border: 1px solid #fecaca; border-radius: 10px; background: #fff7f7; }
.target-list { margin-top: 12px; }
.next-actions { display: flex; gap: 8px; margin-top: 16px; }
.drawer-steps { margin-bottom: 16px; }
.drawer-form { margin-top: 8px; }
.install-panel { margin-top: 16px; border: 1px solid #dbeafe; background: #eff6ff; border-radius: 14px; padding: 14px; }
.install-title { font-weight: 800; margin-bottom: 4px; }
.command-block { margin-top: 12px; }
.command-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; font-weight: 700; color: #1f2937; }
.command-block pre { white-space: pre-wrap; word-break: break-all; background: #111827; color: #e5e7eb; padding: 12px; border-radius: 10px; margin: 0; }
@media (max-width: 900px) { .publish-hero, .inline-control { flex-direction: column; align-items: stretch; } .hero-actions { flex-direction: column; } }
</style>

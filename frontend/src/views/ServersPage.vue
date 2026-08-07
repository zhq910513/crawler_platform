<template>
  <div class="page-card servers-page">
    <div class="toolbar hero-toolbar">
      <div>
        <h3>执行节点</h3>
        <p class="muted">接入服务器后，平台会在这些节点上运行爬虫任务。</p>
      </div>
      <div>
        <el-button v-if="sessionState.user?.isSuperAdmin" type="primary" @click="openOnboarding">接入执行节点</el-button>
        <el-button v-if="sessionState.user?.isSuperAdmin" @click="dialogVisible = true">手工新增</el-button>
        <el-button @click="load">刷新</el-button>
      </div>
    </div>

    <el-table :data="rows" stripe>
      <el-table-column label="执行节点" min-width="220">
        <template #default="s">
          <div class="server-name">{{ s.row.serverName }}</div>
          <div class="muted">{{ s.row.serverIp || '-' }}</div>
        </template>
      </el-table-column>
      <el-table-column label="管理状态"><template #default="s">{{ zh(s.row.manageStatus) }}</template></el-table-column>
      <el-table-column label="健康状态"><template #default="s"><el-tag :type="healthTag(s.row.healthStatus)" effect="light">{{ zh(s.row.healthStatus) }}</el-tag></template></el-table-column>
      <el-table-column label="容量状态"><template #default="s"><el-tag :type="capacityTag(s.row.capacityStatus)" effect="light">{{ zh(s.row.capacityStatus) }}</el-tag></template></el-table-column>
      <el-table-column label="资源使用" min-width="260">
        <template #default="s">
          <div class="metric-line">处理器 <el-progress :percentage="percent(s.row.metrics?.cpuUsage)" :show-text="true" /></div>
          <div class="metric-line">内存 <el-progress :percentage="percent(s.row.metrics?.memoryUsage)" :show-text="true" /></div>
          <div class="metric-line">磁盘 <el-progress :percentage="percent(s.row.metrics?.diskUsage)" :show-text="true" /></div>
          <div class="metric-line">文件数 <el-progress :percentage="percent(s.row.metrics?.inodeUsage)" :show-text="true" /></div>
        </template>
      </el-table-column>
      <el-table-column label="可用槽位" min-width="140">
        <template #default="s">
          <div>{{ s.row.metrics?.availableSlots ?? '-' }} / {{ s.row.metrics?.maxSlots ?? s.row.maxContainerSlots }}</div>
          <div class="muted">运行中：{{ s.row.metrics?.runningContainers ?? 0 }}</div>
        </template>
      </el-table-column>
      <el-table-column label="环境检查" min-width="180">
        <template #default="s">
          <div>容器服务：{{ zh(s.row.metrics?.dockerStatus || '-') }}</div>
          <div>执行权限：{{ boolText(s.row.metrics?.dockerSockAccessible) }}</div>
          <div>数据目录：{{ boolText(s.row.metrics?.projectDataRootWritable) }}</div>
          <div>时区：{{ s.row.metrics?.timezone || '-' }}</div>
        </template>
      </el-table-column>
      <el-table-column label="最后心跳" min-width="170"><template #default="s">{{ formatTime(s.row.metrics?.lastHeartbeatAt) }}</template></el-table-column>
      <el-table-column label="最近异常" min-width="220"><template #default="s">{{ s.row.metrics?.lastError || '-' }}</template></el-table-column>
    </el-table>

    <el-dialog v-model="onboardingVisible" title="接入执行节点" width="860px" class="onboarding-dialog">
      <el-steps :active="joinResult ? 2 : 1" simple class="wizard-steps">
        <el-step title="填写服务器信息" />
        <el-step title="复制命令执行" />
        <el-step title="等待节点上线" />
      </el-steps>

      <el-alert class="guide-alert" type="info" :closable="false" show-icon title="接入凭证会由系统自动生成并写入安装命令，不需要单独复制。" />

      <el-form label-position="top" class="onboarding-form">
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="公司"><el-select v-model="joinForm.companyId" @change="applyAutoCodes"><el-option v-for="company in companies" :key="company.companyId" :label="company.companyName" :value="company.companyId" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="接入场景"><el-radio-group v-model="joinForm.installTarget" @change="applyInstallTarget"><el-radio-button label="REMOTE">远程服务器</el-radio-button><el-radio-button label="LOCAL">本机测试</el-radio-button></el-radio-group></el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="服务器名称"><el-input v-model="joinForm.serverName" placeholder="例如：测试服务器01" @blur="applyAutoCodes" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="最大并发"><el-input-number v-model="joinForm.maxContainerSlots" :min="1" :max="100" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="平台访问地址">
          <el-input v-model="joinForm.platformUrl" placeholder="请输入执行节点可以访问的平台地址，例如：http://10.1.0.13:8080" />
          <div class="field-hint">远程服务器不能使用本机地址；请填写目标服务器能访问到的内网地址、外网地址或域名。</div>
        </el-form-item>
        <el-form-item label="工作目录"><el-input v-model="joinForm.workDir" /></el-form-item>
        <el-collapse class="advanced-box">
          <el-collapse-item title="高级设置" name="advanced">
            <el-row :gutter="16">
              <el-col :span="12"><el-form-item label="服务器编号"><el-input v-model="joinForm.serverCode" /></el-form-item></el-col>
              <el-col :span="12"><el-form-item label="执行器编号"><el-input v-model="joinForm.agentCode" /></el-form-item></el-col>
            </el-row>
          </el-collapse-item>
        </el-collapse>
      </el-form>

      <div v-if="addressWarning" class="warning-card">{{ addressWarning }}</div>

      <div v-if="joinResult" class="install-panel">
        <div class="install-header">
          <div>
            <div class="install-title">接入命令已生成</div>
            <div class="muted">该命令包含一次性接入凭证，请只发送给可信运维人员。凭证使用后会自动失效。</div>
          </div>
          <el-tag type="success" effect="light">有效期：{{ formatTime(joinResult.expiresAt) }}</el-tag>
        </div>
        <div class="command-block">
          <div class="command-title"><span>第一步：在目标服务器验证连通性</span><el-button size="small" @click="copyText(joinResult.connectivityCommand || '')">复制</el-button></div>
          <pre>{{ joinResult.connectivityCommand }}</pre>
        </div>
        <div class="command-block">
          <div class="command-title"><span>第二步：安装并接入执行节点</span><el-button size="small" type="primary" @click="copyText(joinResult.installCommand)">复制</el-button></div>
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
        <el-form-item label="公司"><el-select v-model="form.companyId"><el-option v-for="company in companies" :key="company.companyId" :label="company.companyName" :value="company.companyId" /></el-select></el-form-item>
        <el-form-item label="节点标识"><el-input v-model="form.serverCode" /></el-form-item>
        <el-form-item label="节点名称"><el-input v-model="form.serverName" /></el-form-item>
        <el-form-item label="服务器地址"><el-input v-model="form.serverIp" /></el-form-item>
        <el-form-item label="最大并发"><el-input-number v-model="form.maxContainerSlots" :min="1" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createAgentJoinToken, createServer, listCompanies, listServers } from '../api/platform'
import { sessionState } from '../stores/session'
import type { AgentJoinTokenResult, Company, ServerNode } from '../types/api'
import { formatTime, zh } from '../utils/dictionaries'

const rows = ref<ServerNode[]>([])
const companies = ref<Company[]>([])
const dialogVisible = ref(false)
const onboardingVisible = ref(false)
const joinResult = ref<AgentJoinTokenResult | null>(null)
const joinForm = reactive({ companyId: 0, serverCode: '', serverName: '', agentCode: '', agentName: '', maxContainerSlots: 2, workDir: '/var/lib/crawler-agent', installTarget: 'REMOTE' as 'LOCAL' | 'REMOTE', platformUrl: '' })
const form = reactive({ companyId: 0, serverCode: '', serverName: '', serverIp: '', maxContainerSlots: 4 })

function percent(value?: number | null) { if (value === null || value === undefined || Number.isNaN(Number(value))) return 0; return Math.max(0, Math.min(100, Math.round(Number(value)))) }
function boolText(value?: boolean | null) { if (value === null || value === undefined) return '-'; return value ? '可用' : '不可用' }
function healthTag(status: string) { if (status === 'HEALTHY') return 'success'; if (status === 'OFFLINE' || status === 'UNHEALTHY') return 'danger'; return 'warning' }
function capacityTag(status: string) { if (status === 'NORMAL') return 'success'; if (status === 'EXHAUSTED' || status === 'FULL' || status === 'DRAINED') return 'danger'; return 'warning' }
function isLoopbackUrl(value: string) { try { const host = new URL(value).hostname.toLowerCase(); return ['127.0.0.1', 'localhost', '0.0.0.0', '::1'].includes(host) } catch { return false } }
function currentOrigin() { return window.location.origin }
function slug(value: string) { return (value || 'server').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40) || 'server' }
const addressWarning = computed(() => {
  if (!joinForm.platformUrl) return '请填写执行节点可以访问的平台地址。'
  try { new URL(joinForm.platformUrl) } catch { return '平台访问地址格式不正确。' }
  if (joinForm.installTarget === 'REMOTE' && isLoopbackUrl(joinForm.platformUrl)) return '远程服务器不能使用本机地址，请填写内网地址、外网地址或域名。'
  return ''
})
function applyAutoCodes() {
  const base = slug(joinForm.serverName || 'test-server')
  if (!joinForm.serverCode) joinForm.serverCode = base
  if (!joinForm.agentCode) joinForm.agentCode = `${base}-executor`
}
function applyInstallTarget() {
  if (joinForm.installTarget === 'LOCAL') {
    joinForm.platformUrl = joinForm.platformUrl || currentOrigin()
    joinForm.workDir = '/var/lib/crawler-agent'
  } else {
    joinForm.platformUrl = currentOrigin()
    if (isLoopbackUrl(joinForm.platformUrl)) joinForm.platformUrl = ''
    joinForm.workDir = '/var/lib/crawler-agent'
  }
}
function openOnboarding() {
  joinResult.value = null
  onboardingVisible.value = true
  if (!joinForm.companyId) joinForm.companyId = form.companyId
  if (!joinForm.serverName) joinForm.serverName = '测试服务器01'
  applyAutoCodes()
  applyInstallTarget()
}
async function load() {
  companies.value = await listCompanies()
  if (!form.companyId) form.companyId = sessionState.user?.companyId || companies.value[0]?.companyId || 0
  if (!joinForm.companyId) joinForm.companyId = form.companyId
  rows.value = await listServers(sessionState.user?.isSuperAdmin ? undefined : sessionState.user?.companyId || undefined)
}
async function createJoin() {
  if (addressWarning.value) { ElMessage.warning(addressWarning.value); return }
  applyAutoCodes()
  joinResult.value = await createAgentJoinToken({ ...joinForm, agentName: joinForm.agentName || joinForm.serverName, labels: {}, capabilities: {} })
  ElMessage.success('接入命令已生成')
}
async function copyText(text: string) {
  if (!text) return
  await navigator.clipboard.writeText(text)
  ElMessage.success('已复制')
}
async function save() { await createServer(form); dialogVisible.value = false; await load() }
onMounted(load)
</script>
<style scoped>
.server-name { font-weight: 700; color: #111827; }
.hero-toolbar { align-items: flex-start; }
.hero-toolbar h3 { margin: 0 0 6px; }
.metric-line { display: grid; grid-template-columns: 56px 1fr; gap: 8px; align-items: center; margin-bottom: 6px; }
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
</style>

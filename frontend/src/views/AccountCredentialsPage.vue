<template>
  <div class="account-page">
    <div class="metric-grid">
      <div class="metric-card"><div class="metric-label">账号总数</div><div class="metric-value">{{ credentials.length }}</div></div>
      <div class="metric-card"><div class="metric-label">健康账号</div><div class="metric-value success">{{ healthyCount }}</div></div>
      <div class="metric-card"><div class="metric-label">对象绑定</div><div class="metric-value">{{ bindings.length }}</div></div>
      <div class="metric-card"><div class="metric-label">占用中</div><div class="metric-value warning">{{ activeLeaseCount }}</div></div>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span class="card-title">账号资源</span>
          <div class="card-actions"><el-button type="primary" @click="openReportDialog">登记状态</el-button></div>
        </div>
      </template>
      <el-form :inline="true" class="filter-bar">
        <el-form-item label="公司" v-if="sessionState.user?.isSuperAdmin"><el-select v-model="query.companyId" clearable placeholder="全部公司" style="width: 220px"><el-option v-for="c in companies" :key="c.companyId" :label="c.companyName" :value="c.companyId" /></el-select></el-form-item><el-form-item v-else label="当前公司"><el-input :model-value="currentCompanyName" disabled style="width: 220px" /></el-form-item>
        <el-form-item label="平台"><el-input v-model="query.platformCode" placeholder="请输入平台名称" clearable /></el-form-item>
        <el-form-item label="账号"><el-input v-model="query.credentialKey" placeholder="请输入账号标识" clearable /></el-form-item>
        <el-form-item><el-button type="primary" @click="reloadAll">查询</el-button><el-button @click="resetQuery">重置</el-button></el-form-item>
      </el-form>
      <el-table :data="credentials" stripe class="pretty-table">
        <el-table-column label="公司" width="130"><template #default="s">{{ companyName(s.row.companyId, s.row.companyCode) }}</template></el-table-column>
        <el-table-column label="平台" width="120"><template #default="s">{{ platformName(s.row.platformCode) }}</template></el-table-column>
        <el-table-column label="账号" min-width="190" show-overflow-tooltip><template #default="s"><span class="identifier-text">{{ accountName(s.row) }}</span></template></el-table-column>
        <el-table-column label="启用" width="86" align="center"><template #default="{ row }"><el-switch v-model="row.enabled" @change="(v: boolean) => toggleEnabled(row, v)" /></template></el-table-column>
        <el-table-column label="健康" width="110" align="center"><template #default="s"><el-tag :type="statusType(s.row.healthStatus)" effect="light">{{ zh(s.row.healthStatus) }}</el-tag></template></el-table-column>
        <el-table-column label="登录态" width="120"><template #default="s">{{ zh(s.row.loginStatus) }}</template></el-table-column>
        <el-table-column label="使用状态" width="120"><template #default="s">{{ zh(s.row.usageStatus) }}</template></el-table-column>
        <el-table-column label="最近结果" width="140"><template #default="s">{{ statusCodeText(s.row.lastStatusCode) }}</template></el-table-column>
        <el-table-column label="最近验证" width="170"><template #default="s">{{ formatTime(s.row.lastVerifiedAt) }}</template></el-table-column>
        <el-table-column label="异常摘要" min-width="220" show-overflow-tooltip><template #default="s">{{ s.row.lastErrorSummary || '-' }}</template></el-table-column>
        <el-table-column label="操作" width="108" fixed="right" align="center"><template #default="{ row }"><el-button size="small" @click="openEvents(row)">查看</el-button></template></el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never">
      <template #header><div class="card-header"><span class="card-title">对象绑定</span><el-button @click="loadBindings">刷新</el-button></div></template>
      <el-table :data="bindings" stripe class="pretty-table">
        <el-table-column label="公司" width="130"><template #default="s">{{ companyName(s.row.companyId, s.row.companyCode) }}</template></el-table-column>
        <el-table-column label="平台" width="120"><template #default="s">{{ platformName(s.row.platformCode) }}</template></el-table-column>
        <el-table-column label="对象类型" width="110"><template #default="s">{{ subjectTypeText(s.row.subjectType) }}</template></el-table-column>
        <el-table-column label="对象" min-width="200" show-overflow-tooltip><template #default="s">{{ s.row.subjectName || s.row.subjectKey || '-' }}</template></el-table-column>
        <el-table-column label="绑定账号" min-width="170" show-overflow-tooltip><template #default="s"><span class="identifier-text">{{ s.row.credentialKey || '-' }}</span></template></el-table-column>
        <el-table-column label="状态" width="110"><template #default="s">{{ zh(s.row.bindingStatus) }}</template></el-table-column>
        <el-table-column label="换绑" width="120"><template #default="s">{{ zh(s.row.rebindingPolicy) }}</template></el-table-column>
        <el-table-column label="最近成功" width="170"><template #default="s">{{ formatTime(s.row.lastSuccessAt) }}</template></el-table-column>
        <el-table-column label="最近异常" min-width="180" show-overflow-tooltip><template #default="s">{{ s.row.lastErrorSummary || '-' }}</template></el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never">
      <template #header><div class="card-header"><span class="card-title">账号占用</span><el-button @click="loadLeases">刷新</el-button></div></template>
      <el-table :data="leases" stripe class="pretty-table">
        <el-table-column label="公司" width="130"><template #default="s">{{ companyName(s.row.companyId, s.row.companyCode) }}</template></el-table-column>
        <el-table-column label="平台" width="120"><template #default="s">{{ platformName(s.row.platformCode) }}</template></el-table-column>
        <el-table-column label="账号" min-width="170" show-overflow-tooltip><template #default="s"><span class="identifier-text">{{ s.row.credentialKey || '-' }}</span></template></el-table-column>
        <el-table-column label="用途" width="120"><template #default="s">{{ slotName(s.row.slot) }}</template></el-table-column>
        <el-table-column label="状态" width="110"><template #default="s"><el-tag :type="leaseTag(s.row.leaseStatus)" effect="light">{{ zh(s.row.leaseStatus) }}</el-tag></template></el-table-column>
        <el-table-column label="执行节点" width="140"><template #default="s">{{ s.row.agentCode || '-' }}</template></el-table-column>
        <el-table-column label="执行编号" width="110"><template #default="s">{{ s.row.runId || '-' }}</template></el-table-column>
        <el-table-column label="占用至" width="170"><template #default="s">{{ formatTime(s.row.leaseUntil) }}</template></el-table-column>
        <el-table-column label="释放原因" min-width="160" show-overflow-tooltip><template #default="s">{{ s.row.releaseReason || '-' }}</template></el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="eventsVisible" title="账号状态记录" width="900px">
      <el-table :data="events" stripe max-height="520">
        <el-table-column label="时间" width="170"><template #default="s">{{ formatTime(s.row.createdAt) }}</template></el-table-column>
        <el-table-column label="来源" width="110"><template #default="s">{{ sourceText(s.row.source) }}</template></el-table-column>
        <el-table-column label="结果" width="150"><template #default="s">{{ statusCodeText(s.row.statusCode) }}</template></el-table-column>
        <el-table-column label="级别" width="100"><template #default="s">{{ zh(s.row.severity) }}</template></el-table-column>
        <el-table-column label="执行节点" width="140"><template #default="s">{{ s.row.agentCode || '-' }}</template></el-table-column>
        <el-table-column label="说明" min-width="260" show-overflow-tooltip><template #default="s">{{ s.row.messageSanitized || '-' }}</template></el-table-column>
      </el-table>
    </el-dialog>

    <el-dialog v-model="reportVisible" title="登记账号状态" width="560px">
      <el-form label-position="top">
        <el-form-item label="公司" v-if="sessionState.user?.isSuperAdmin"><el-select v-model="reportForm.companyId" placeholder="选择公司"><el-option v-for="c in companies" :key="c.companyId" :label="c.companyName" :value="c.companyId" /></el-select></el-form-item><el-form-item v-else label="当前公司"><el-input :model-value="currentCompanyName" disabled /></el-form-item>
        <el-form-item label="平台"><el-input v-model="reportForm.platformCode" placeholder="请输入平台名称" /></el-form-item>
        <el-form-item label="账号"><el-input v-model="reportForm.credentialKey" placeholder="请输入账号标识" /></el-form-item>
        <el-form-item label="账号名称"><el-input v-model="reportForm.credentialName" placeholder="可选" /></el-form-item>
        <el-form-item label="状态"><el-select v-model="reportForm.statusCode" filterable><el-option v-for="item in statusCodeOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
        <el-form-item label="说明"><el-input v-model="reportForm.message" type="textarea" :rows="3" placeholder="请填写简要说明" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="reportVisible=false">取消</el-button><el-button type="primary" @click="submitReport">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createAccountStatusEvent, listAccountCredentials, listAccountStatusEvents, listCompanies, setAccountCredentialEnabled, listCredentialSubjectBindings, listCredentialLeases } from '../api/platform'
import type { AccountCredential, AccountStatusEvent, Company, CredentialSubjectBinding, CredentialLease } from '../types/api'
import { formatTime, zh } from '../utils/dictionaries'
import { sessionState } from '../stores/session'

const companies = ref<Company[]>([])
const credentials = ref<AccountCredential[]>([])
const events = ref<AccountStatusEvent[]>([])
const bindings = ref<CredentialSubjectBinding[]>([])
const leases = ref<CredentialLease[]>([])
const eventsVisible = ref(false)
const reportVisible = ref(false)
const query = reactive<{ companyId?: number; platformCode: string; credentialKey: string }>({ platformCode: '', credentialKey: '' })
const reportForm = reactive({ companyId: undefined as number | undefined, platformCode: '', credentialKey: '', credentialName: '', statusCode: 'LOGIN_OK', message: '' })
const statusCodeOptions = [
  { value: 'LOGIN_OK', label: '登录正常' }, { value: 'COOKIE_OK', label: '浏览器凭证正常' }, { value: 'TOKEN_OK', label: '接口授权正常' },
  { value: 'COOKIE_EXPIRED', label: '浏览器凭证过期' }, { value: 'COOKIE_INVALID', label: '浏览器凭证无效' }, { value: 'TOKEN_EXPIRED', label: '接口授权过期' }, { value: 'TOKEN_INVALID', label: '接口授权无效' },
  { value: 'LOGIN_FAILED', label: '登录失败' }, { value: 'CAPTCHA_REQUIRED', label: '需要验证码' }, { value: 'EMAIL_VERIFY_REQUIRED', label: '需要邮箱验证' }, { value: 'PHONE_VERIFY_REQUIRED', label: '需要手机验证' }, { value: 'TWO_FACTOR_REQUIRED', label: '需要二次验证' },
  { value: 'RATE_LIMITED', label: '访问受限' }, { value: 'QUOTA_LIMITED', label: '额度用尽' }, { value: 'NETWORK_ERROR', label: '网络异常' }, { value: 'PLATFORM_5XX', label: '目标平台异常' }, { value: 'UNKNOWN_AUTH_ERROR', label: '授权异常' },
]
const statusCodeMap = Object.fromEntries(statusCodeOptions.map((item) => [item.value, item.label]))
const healthyCount = computed(() => credentials.value.filter((item) => item.healthStatus === 'HEALTHY').length)
const activeLeaseCount = computed(() => leases.value.filter((item) => item.leaseStatus === 'ACTIVE').length)
const currentCompanyName = computed(() => companies.value.find((item) => item.companyId === sessionState.user?.companyId)?.companyName || '归属公司')

onMounted(async () => { companies.value = await listCompanies(); if (!sessionState.user?.isSuperAdmin) { query.companyId = sessionState.user?.companyId || undefined; reportForm.companyId = sessionState.user?.companyId || undefined } await reloadAll() })
async function reloadAll() { await Promise.all([loadCredentials(), loadBindings(), loadLeases()]) }
async function loadCredentials() { credentials.value = await listAccountCredentials({ companyId: query.companyId, platformCode: query.platformCode || undefined, credentialKey: query.credentialKey || undefined }) }
async function loadBindings() { bindings.value = await listCredentialSubjectBindings({ companyId: query.companyId, platformCode: query.platformCode || undefined, credentialKey: query.credentialKey || undefined }) }
async function loadLeases() { leases.value = await listCredentialLeases({ companyId: query.companyId, platformCode: query.platformCode || undefined, credentialKey: query.credentialKey || undefined }) }
function resetQuery() { query.companyId = sessionState.user?.isSuperAdmin ? undefined : sessionState.user?.companyId || undefined; query.platformCode = ''; query.credentialKey = ''; void reloadAll() }
function statusType(value: string) { if (value === 'HEALTHY') return 'success'; if (['EXPIRED','INVALID','NEED_VERIFY','DISABLED'].includes(value)) return 'danger'; if (value === 'WARNING') return 'warning'; return 'info' }
function leaseTag(value: string) { if (value === 'ACTIVE') return 'warning'; if (value === 'RELEASED') return 'info'; if (value === 'EXPIRED') return 'danger'; return 'info' }
function companyName(companyId: number, fallback: string) { return companies.value.find((item) => item.companyId === companyId)?.companyName || fallback || '-' }
function platformName(value: string) { const map: Record<string, string> = { shopee: 'Shopee', oilchem: '隆众', jdl: '京东物流', amazon: 'Amazon', commercehub: 'CommerceHub', feishu: '飞书', baidu_b2b: '百度爱采购' }; return map[value] || value || '-' }
function accountName(row: AccountCredential) { return row.credentialName || row.credentialKey || '-' }
function statusCodeText(value?: string | null) { if (!value) return '-'; return statusCodeMap[value] || zh(value) }
function sourceText(value?: string | null) { const map: Record<string, string> = { ADMIN: '人工', TASK: '任务', AGENT: '节点', SYSTEM: '系统' }; return value ? (map[value] || zh(value)) : '-' }
function slotName(value?: string | null) { const map: Record<string, string> = { login: '登录', api: '接口', worker: '采集', queryAccount: '查询', reportAccounts: '报表', writer: '写入' }; return value ? (map[value] || value) : '-' }
function subjectTypeText(value?: string | null) { const map: Record<string, string> = { company: '公司', shop: '店铺', product: '商品', order: '订单', keyword: '关键词' }; return value ? (map[value] || value) : '-' }
async function toggleEnabled(row: AccountCredential, enabled: boolean) { const updated = await setAccountCredentialEnabled(row.credentialId, enabled, enabled ? '前端启用账号' : '前端禁用账号'); Object.assign(row, updated) }
async function openEvents(row: AccountCredential) { events.value = await listAccountStatusEvents(row.credentialId); eventsVisible.value = true }
function openReportDialog() { if (!sessionState.user?.isSuperAdmin) reportForm.companyId = sessionState.user?.companyId || undefined; reportVisible.value = true }
async function submitReport() { await createAccountStatusEvent({ ...reportForm, source: 'ADMIN', severity: reportForm.statusCode.endsWith('_OK') ? 'INFO' : 'WARNING' }); ElMessage.success('账号状态已登记'); reportVisible.value = false; await reloadAll() }
</script>

<style scoped>
.account-page { display: flex; flex-direction: column; gap: 16px; }
.pretty-table { width: 100%; }
</style>

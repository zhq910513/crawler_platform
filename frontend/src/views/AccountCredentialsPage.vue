<template>
  <div class="page">
    <el-alert title="前端合约：公司管理公司边界；数据库配置管理公司资源；平台账号维护账号状态；项目管理由 CI/CD 自动发现任务；任务调度给平台任务分配账号槽位。账号状态来自任务反馈/人工测试/Agent 探测，不高频扫描客户缓存库。" type="success" show-icon :closable="false" />
    <el-card shadow="never">
      <template #header><div class="card-header"><span>账号状态中心</span><el-button type="primary" @click="openReportDialog">手动上报状态</el-button></div></template>
      <el-form :inline="true" class="filter-bar">
        <el-form-item label="公司"><el-select v-model="query.companyId" clearable placeholder="全部公司" style="width: 220px"><el-option v-for="c in companies" :key="c.companyId" :label="c.companyName" :value="c.companyId" /></el-select></el-form-item>
        <el-form-item label="平台"><el-input v-model="query.platformCode" placeholder="shopee / oilchem" clearable /></el-form-item>
        <el-form-item label="账号唯一值"><el-input v-model="query.credentialKey" placeholder="credentialKey" clearable /></el-form-item>
        <el-form-item><el-button type="primary" @click="loadCredentials">查询</el-button></el-form-item>
      </el-form>
      <el-alert title="平台展示的是账号最后已知状态：来自任务运行反馈、人工测试、Agent 探测或过期时间推导；平台不会高频访问客户账号缓存库。" type="info" show-icon :closable="false" class="tip" />
      <el-table :data="credentials" border stripe>
        <el-table-column prop="companyCode" label="公司" width="120" />
        <el-table-column prop="platformCode" label="平台" width="120" />
        <el-table-column prop="credentialKey" label="账号唯一值" min-width="190" />
        <el-table-column prop="enabled" label="启用" width="90"><template #default="{ row }"><el-switch v-model="row.enabled" @change="(v: boolean) => toggleEnabled(row, v)" /></template></el-table-column>
        <el-table-column prop="healthStatus" label="健康" width="120"><template #default="{ row }"><el-tag :type="statusType(row.healthStatus)">{{ row.healthStatus }}</el-tag></template></el-table-column>
        <el-table-column prop="loginStatus" label="登录态" width="140" />
        <el-table-column prop="usageStatus" label="使用" width="120" />
        <el-table-column prop="lastStatusCode" label="最后状态码" width="160" />
        <el-table-column prop="lastVerifiedAt" label="最后验证" width="180" />
        <el-table-column prop="statusFreshUntil" label="状态可信至" width="180" />
        <el-table-column prop="lastErrorSummary" label="最后错误" min-width="220" show-overflow-tooltip />
        <el-table-column label="操作" width="120" fixed="right"><template #default="{ row }"><el-button size="small" @click="openEvents(row)">事件</el-button></template></el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never">
      <template #header><div class="card-header"><span>对象账号绑定</span><el-button @click="loadBindings">刷新</el-button></div></template>
      <el-table :data="bindings" border stripe>
        <el-table-column prop="companyCode" label="公司" width="120" />
        <el-table-column prop="platformCode" label="平台" width="120" />
        <el-table-column prop="subjectType" label="对象类型" width="110" />
        <el-table-column prop="subjectKey" label="对象唯一值" min-width="180" show-overflow-tooltip />
        <el-table-column prop="credentialKey" label="绑定账号" min-width="160" show-overflow-tooltip />
        <el-table-column prop="bindingStatus" label="绑定状态" width="110" />
        <el-table-column prop="rebindingPolicy" label="换绑策略" width="140" />
        <el-table-column prop="lastSuccessAt" label="最近成功" width="180" />
        <el-table-column prop="lastErrorSummary" label="最近错误" min-width="180" show-overflow-tooltip />
      </el-table>
    </el-card>

    <el-card shadow="never">
      <template #header><div class="card-header"><span>账号租约</span><el-button @click="loadLeases">刷新</el-button></div></template>
      <el-alert title="账号池/对象亲和任务执行时会申请租约；同一账号有 ACTIVE 租约时，其他任务不能重复占用。" type="warning" show-icon :closable="false" class="tip" />
      <el-table :data="leases" border stripe>
        <el-table-column prop="companyCode" label="公司" width="120" />
        <el-table-column prop="platformCode" label="平台" width="120" />
        <el-table-column prop="credentialKey" label="账号唯一值" min-width="160" show-overflow-tooltip />
        <el-table-column prop="slot" label="槽位" width="100" />
        <el-table-column prop="leaseStatus" label="租约状态" width="120" />
        <el-table-column prop="agentCode" label="Agent" width="140" />
        <el-table-column prop="runId" label="Run" width="100" />
        <el-table-column prop="leaseUntil" label="租约到期" width="180" />
        <el-table-column prop="releaseReason" label="释放原因" min-width="160" show-overflow-tooltip />
      </el-table>
    </el-card>

    <el-dialog v-model="eventsVisible" title="账号状态事件" width="900px">
      <el-table :data="events" border max-height="520">
        <el-table-column prop="createdAt" label="时间" width="180" />
        <el-table-column prop="source" label="来源" width="120" />
        <el-table-column prop="statusCode" label="状态码" width="160" />
        <el-table-column prop="severity" label="级别" width="100" />
        <el-table-column prop="agentCode" label="Agent" width="140" />
        <el-table-column prop="messageSanitized" label="消息" min-width="260" show-overflow-tooltip />
      </el-table>
    </el-dialog>

    <el-dialog v-model="reportVisible" title="手动上报账号状态" width="560px">
      <el-form label-position="top">
        <el-form-item label="公司"><el-select v-model="reportForm.companyId" placeholder="选择公司"><el-option v-for="c in companies" :key="c.companyId" :label="c.companyName" :value="c.companyId" /></el-select></el-form-item>
        <el-form-item label="平台编码"><el-input v-model="reportForm.platformCode" placeholder="shopee" /></el-form-item>
        <el-form-item label="账号唯一值"><el-input v-model="reportForm.credentialKey" placeholder="shopee_ulike_id_local" /></el-form-item>
        <el-form-item label="账号名称"><el-input v-model="reportForm.credentialName" placeholder="可选" /></el-form-item>
        <el-form-item label="状态码"><el-select v-model="reportForm.statusCode" filterable><el-option v-for="code in statusCodes" :key="code" :label="code" :value="code" /></el-select></el-form-item>
        <el-form-item label="消息"><el-input v-model="reportForm.message" type="textarea" :rows="3" placeholder="不要填写 Cookie、Token、密码等敏感内容" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="reportVisible=false">取消</el-button><el-button type="primary" @click="submitReport">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createAccountStatusEvent, listAccountCredentials, listAccountStatusEvents, listCompanies, setAccountCredentialEnabled, listCredentialSubjectBindings, listCredentialLeases } from '../api/platform'
import type { AccountCredential, AccountStatusEvent, Company, CredentialSubjectBinding, CredentialLease } from '../types/api'

const companies = ref<Company[]>([])
const credentials = ref<AccountCredential[]>([])
const events = ref<AccountStatusEvent[]>([])
const bindings = ref<CredentialSubjectBinding[]>([])
const leases = ref<CredentialLease[]>([])
const eventsVisible = ref(false)
const reportVisible = ref(false)
const query = reactive<{ companyId?: number; platformCode: string; credentialKey: string }>({ platformCode: '', credentialKey: '' })
const reportForm = reactive({ companyId: undefined as number | undefined, platformCode: '', credentialKey: '', credentialName: '', statusCode: 'LOGIN_OK', message: '' })
const statusCodes = ['LOGIN_OK', 'COOKIE_OK', 'TOKEN_OK', 'COOKIE_EXPIRED', 'COOKIE_INVALID', 'TOKEN_EXPIRED', 'TOKEN_INVALID', 'LOGIN_FAILED', 'CAPTCHA_REQUIRED', 'EMAIL_VERIFY_REQUIRED', 'PHONE_VERIFY_REQUIRED', 'TWO_FACTOR_REQUIRED', 'RATE_LIMITED', 'QUOTA_LIMITED', 'NETWORK_ERROR', 'PLATFORM_5XX', 'UNKNOWN_AUTH_ERROR']

onMounted(async () => { companies.value = await listCompanies(); await loadCredentials(); await loadBindings(); await loadLeases() })
async function loadCredentials() { credentials.value = await listAccountCredentials({ companyId: query.companyId, platformCode: query.platformCode || undefined, credentialKey: query.credentialKey || undefined }) }
async function loadBindings() { bindings.value = await listCredentialSubjectBindings({ companyId: query.companyId, platformCode: query.platformCode || undefined, credentialKey: query.credentialKey || undefined }) }
async function loadLeases() { leases.value = await listCredentialLeases({ companyId: query.companyId, platformCode: query.platformCode || undefined, credentialKey: query.credentialKey || undefined }) }
function statusType(value: string) { if (value === 'HEALTHY') return 'success'; if (['EXPIRED','INVALID','NEED_VERIFY','DISABLED'].includes(value)) return 'danger'; if (value === 'WARNING') return 'warning'; return 'info' }
async function toggleEnabled(row: AccountCredential, enabled: boolean) { const updated = await setAccountCredentialEnabled(row.credentialId, enabled, enabled ? '前端启用账号' : '前端禁用账号'); Object.assign(row, updated) }
async function openEvents(row: AccountCredential) { events.value = await listAccountStatusEvents(row.credentialId); eventsVisible.value = true }
function openReportDialog() { reportVisible.value = true }
async function submitReport() { await createAccountStatusEvent({ ...reportForm, source: 'ADMIN', severity: reportForm.statusCode.endsWith('_OK') ? 'INFO' : 'WARNING' }); ElMessage.success('账号状态已上报'); reportVisible.value = false; await loadCredentials(); await loadBindings() }
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 600; }
.filter-bar { margin-bottom: 6px; }
.tip { margin: 8px 0 14px; }
</style>

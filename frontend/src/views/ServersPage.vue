<template>
  <div class="page-card">
    <div class="toolbar">
      <el-button v-if="sessionState.user?.isSuperAdmin" type="primary" @click="dialogVisible = true">新增服务器</el-button>
      <el-button @click="load">刷新</el-button>
    </div>
    <el-table :data="rows" border>
      <el-table-column label="服务器" min-width="220">
        <template #default="s">
          <div class="server-name">{{ s.row.serverName }}</div>
          <div class="muted">{{ s.row.serverCode }} / {{ s.row.serverIp || '-' }}</div>
        </template>
      </el-table-column>
      <el-table-column label="管理状态"><template #default="s">{{ zh(s.row.manageStatus) }}</template></el-table-column>
      <el-table-column label="健康状态"><template #default="s"><el-tag :type="healthTag(s.row.healthStatus)">{{ zh(s.row.healthStatus) }}</el-tag></template></el-table-column>
      <el-table-column label="容量状态"><template #default="s"><el-tag :type="capacityTag(s.row.capacityStatus)">{{ zh(s.row.capacityStatus) }}</el-tag></template></el-table-column>
      <el-table-column label="资源使用" min-width="260">
        <template #default="s">
          <div class="metric-line">CPU <el-progress :percentage="percent(s.row.metrics?.cpuUsage)" :show-text="true" /></div>
          <div class="metric-line">内存 <el-progress :percentage="percent(s.row.metrics?.memoryUsage)" :show-text="true" /></div>
          <div class="metric-line">磁盘 <el-progress :percentage="percent(s.row.metrics?.diskUsage)" :show-text="true" /></div>
          <div class="metric-line">inode <el-progress :percentage="percent(s.row.metrics?.inodeUsage)" :show-text="true" /></div>
        </template>
      </el-table-column>
      <el-table-column label="容器槽位" min-width="150">
        <template #default="s">
          <div>{{ s.row.metrics?.availableSlots ?? '-' }} / {{ s.row.metrics?.maxSlots ?? s.row.maxContainerSlots }}</div>
          <div class="muted">运行容器：{{ s.row.metrics?.runningContainers ?? 0 }}</div>
        </template>
      </el-table-column>
      <el-table-column label="环境检查" min-width="180">
        <template #default="s">
          <div>Docker：{{ zh(s.row.metrics?.dockerStatus || '-') }}</div>
          <div>Docker Sock：{{ boolText(s.row.metrics?.dockerSockAccessible) }}</div>
          <div>数据目录：{{ boolText(s.row.metrics?.projectDataRootWritable) }}</div>
          <div>时区：{{ s.row.metrics?.timezone || '-' }}</div>
        </template>
      </el-table-column>
      <el-table-column label="最后心跳" min-width="170"><template #default="s">{{ formatTime(s.row.metrics?.lastHeartbeatAt) }}</template></el-table-column>
      <el-table-column label="最近错误" min-width="220"><template #default="s">{{ s.row.metrics?.lastError || '-' }}</template></el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新增服务器" width="520px">
      <el-form label-position="top">
        <el-form-item label="公司"><el-select v-model="form.companyId"><el-option v-for="company in companies" :key="company.companyId" :label="company.companyName" :value="company.companyId" /></el-select></el-form-item>
        <el-form-item label="服务器编码"><el-input v-model="form.serverCode" /></el-form-item>
        <el-form-item label="服务器名称"><el-input v-model="form.serverName" /></el-form-item>
        <el-form-item label="服务器IP"><el-input v-model="form.serverIp" /></el-form-item>
        <el-form-item label="最大容器数"><el-input-number v-model="form.maxContainerSlots" :min="1" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { createServer, listCompanies, listServers } from '../api/platform'
import { sessionState } from '../stores/session'
import type { Company, ServerNode } from '../types/api'
import { formatTime, zh } from '../utils/dictionaries'

const rows = ref<ServerNode[]>([])
const companies = ref<Company[]>([])
const dialogVisible = ref(false)
const form = reactive({ companyId: 0, serverCode: '', serverName: '', serverIp: '', maxContainerSlots: 4 })

function percent(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return 0
  return Math.max(0, Math.min(100, Math.round(Number(value))))
}
function boolText(value?: boolean | null) {
  if (value === null || value === undefined) return '-'
  return value ? '可用' : '不可用'
}
function healthTag(status: string) {
  if (status === 'HEALTHY') return 'success'
  if (status === 'OFFLINE' || status === 'UNHEALTHY') return 'danger'
  return 'warning'
}
function capacityTag(status: string) {
  if (status === 'NORMAL') return 'success'
  if (status === 'EXHAUSTED' || status === 'FULL' || status === 'DRAINED') return 'danger'
  return 'warning'
}
async function load() {
  companies.value = await listCompanies()
  if (!form.companyId) form.companyId = sessionState.user?.companyId || companies.value[0]?.companyId || 0
  rows.value = await listServers(sessionState.user?.isSuperAdmin ? undefined : sessionState.user?.companyId || undefined)
}
async function save() {
  await createServer(form)
  dialogVisible.value = false
  await load()
}
onMounted(load)
</script>
<style scoped>
.server-name { font-weight: 600; }
.metric-line { display: grid; grid-template-columns: 42px 1fr; gap: 8px; align-items: center; margin-bottom: 6px; }
.muted { color: #6b7280; font-size: 12px; }
</style>

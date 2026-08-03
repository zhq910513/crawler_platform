<template>
  <div class="page-card">
    <div class="toolbar"><el-button @click="load">刷新</el-button></div>
    <el-table :data="rows" border>
      <el-table-column label="运行ID" prop="runId" width="90" />
      <el-table-column label="项目ID" prop="projectId" />
      <el-table-column label="任务ID" prop="taskId" />
      <el-table-column label="服务器ID" prop="serverId" />
      <el-table-column label="执行状态"><template #default="s"><el-tag :type="runTag(s.row.runStatus)">{{ zh(s.row.runStatus) }}</el-tag></template></el-table-column>
      <el-table-column label="路由状态"><template #default="s">{{ zh(s.row.routingStatus) }}</template></el-table-column>
      <el-table-column label="日志状态"><template #default="s">{{ zh(s.row.logStatus) }}</template></el-table-column>
      <el-table-column label="错误摘要" min-width="220"><template #default="s">{{ s.row.errorSummary || s.row.errorMessage || '-' }}</template></el-table-column>
      <el-table-column label="创建时间" min-width="170"><template #default="s">{{ formatTime(s.row.createdAt) }}</template></el-table-column>
      <el-table-column label="操作" width="180"><template #default="s"><el-button size="small" @click="openDetail(s.row)">日志诊断</el-button><el-button size="small" @click="downloadLogs(s.row.runId)">下载日志</el-button></template></el-table-column>
    </el-table>

    <el-drawer v-model="drawerVisible" title="运行日志与诊断" size="70%">
      <template v-if="selectedRun">
        <el-descriptions :column="3" border>
          <el-descriptions-item label="运行ID">{{ selectedRun.runId }}</el-descriptions-item>
          <el-descriptions-item label="任务ID">{{ selectedRun.taskId }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ zh(selectedRun.runStatus) }}</el-descriptions-item>
          <el-descriptions-item label="失败阶段">{{ diagnosis?.failedStage || selectedRun.failedStage || '-' }}</el-descriptions-item>
          <el-descriptions-item label="错误类型">{{ diagnosis?.errorType || selectedRun.errorType || '-' }}</el-descriptions-item>
          <el-descriptions-item label="可重试">{{ retryableText(diagnosis?.retryable ?? selectedRun.retryable) }}</el-descriptions-item>
        </el-descriptions>

        <el-alert v-if="diagnosis?.errorSummary || selectedRun.errorSummary" :title="diagnosis?.errorSummary || selectedRun.errorSummary" type="error" show-icon class="detail-block" />

        <h3>生命周期事件</h3>
        <el-timeline>
          <el-timeline-item v-for="event in events" :key="event.eventId" :timestamp="formatTime(event.createdAt)" :type="eventType(event.eventLevel)">
            <b>{{ zh(event.eventType) }}</b>
            <span class="muted"> / {{ event.stage || '-' }}</span>
            <div>{{ event.message || '-' }}</div>
          </el-timeline-item>
        </el-timeline>

        <h3>日志尾部</h3>
        <div class="log-toolbar">
          <el-input v-model="logKeyword" placeholder="关键字过滤" clearable style="width:220px" />
          <el-select v-model="logStream" clearable placeholder="日志流" style="width:120px"><el-option label="stdout" value="stdout" /><el-option label="stderr" value="stderr" /></el-select>
          <el-button @click="loadLogs">刷新日志</el-button>
        </div>
        <pre class="log-box">{{ logText || '暂无日志' }}</pre>
      </template>
    </el-drawer>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { downloadRunLogs, getRunDiagnosis, getRunLogTail, listRunEvents, listRuns } from '../api/platform'
import type { RunDiagnosis, RunEvent, RunRecord } from '../types/api'
import { formatTime, zh } from '../utils/dictionaries'

const rows = ref<RunRecord[]>([])
const drawerVisible = ref(false)
const selectedRun = ref<RunRecord | null>(null)
const events = ref<RunEvent[]>([])
const diagnosis = ref<RunDiagnosis | null>(null)
const logKeyword = ref('')
const logStream = ref('')
const logText = ref('')
const logAfterSeq = ref(0)

const selectedRunId = computed(() => selectedRun.value?.runId || 0)

async function load() {
  rows.value = await listRuns()
}
function runTag(status: string) {
  if (status === 'SUCCEEDED') return 'success'
  if (['FAILED', 'TIMED_OUT', 'LOST', 'CANCELLED'].includes(status)) return 'danger'
  if (['RUNNING', 'STARTING', 'ASSIGNED'].includes(status)) return 'warning'
  return 'info'
}
function eventType(level: string) {
  if (level === 'ERROR' || level === 'CRITICAL') return 'danger'
  if (level === 'WARN' || level === 'WARNING') return 'warning'
  return 'primary'
}
function retryableText(value?: boolean | null) {
  if (value === null || value === undefined) return '-'
  return value ? '建议重试' : '不建议自动重试'
}
async function openDetail(row: RunRecord) {
  selectedRun.value = row
  drawerVisible.value = true
  logAfterSeq.value = 0
  await Promise.all([loadEvents(), loadDiagnosis(), loadLogs()])
}
async function loadEvents() {
  if (!selectedRunId.value) return
  events.value = await listRunEvents(selectedRunId.value)
}
async function loadDiagnosis() {
  if (!selectedRunId.value) return
  diagnosis.value = await getRunDiagnosis(selectedRunId.value)
}
async function loadLogs() {
  if (!selectedRunId.value) return
  const tail = await getRunLogTail(selectedRunId.value, { afterSeq: 0, limit: 300, keyword: logKeyword.value, stream: logStream.value })
  logAfterSeq.value = tail.lastLogSeq
  logText.value = tail.chunks.map((chunk) => chunk.content).join('\n')
}
async function downloadLogs(runId: number) {
  const result = await downloadRunLogs(runId)
  const blob = new Blob([result.content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = result.filename
  link.click()
  URL.revokeObjectURL(url)
  ElMessage.success(result.logTruncated ? '日志已下载，内容已按上限截断' : '日志已下载')
}
onMounted(load)
</script>
<style scoped>
.detail-block { margin: 16px 0; }
.log-toolbar { display: flex; gap: 10px; margin-bottom: 10px; }
.log-box { min-height: 280px; max-height: 520px; overflow: auto; padding: 12px; color: #d1d5db; background: #111827; border-radius: 6px; white-space: pre-wrap; word-break: break-word; }
.muted { color: #6b7280; }
</style>

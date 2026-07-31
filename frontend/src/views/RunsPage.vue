<template>
  <div class="page-card">
    <div class="toolbar"><el-button @click="load">刷新</el-button></div>
    <el-table :data="rows" border><el-table-column label="运行ID" prop="runId" width="90" /><el-table-column label="项目ID" prop="projectId" /><el-table-column label="任务ID" prop="taskId" /><el-table-column label="服务器ID" prop="serverId" /><el-table-column label="执行状态"><template #default="s">{{ zh(s.row.runStatus) }}</template></el-table-column><el-table-column label="路由状态"><template #default="s">{{ zh(s.row.routingStatus) }}</template></el-table-column><el-table-column label="路由原因" prop="routingReason" /><el-table-column label="创建时间"><template #default="s">{{ formatTime(s.row.createdAt) }}</template></el-table-column><el-table-column label="错误信息" prop="errorMessage" /></el-table>
  </div>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listRuns } from '../api/platform'
import type { RunRecord } from '../types/api'
import { formatTime, zh } from '../utils/dictionaries'
const rows = ref<RunRecord[]>([])
async function load() { rows.value = await listRuns() }
onMounted(load)
</script>

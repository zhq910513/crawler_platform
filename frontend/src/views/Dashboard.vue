<template>
  <div>
    <div class="metrics">
      <div class="metric"><div class="muted">任务总数</div><strong>{{ data.task_total || 0 }}</strong></div>
      <div class="metric"><div class="muted">运行中</div><strong>{{ data.running || 0 }}</strong></div>
      <div class="metric"><div class="muted">今日成功</div><strong>{{ data.success_today || 0 }}</strong></div>
      <div class="metric"><div class="muted">今日失败</div><strong>{{ data.failed_today || 0 }}</strong></div>
      <div class="metric"><div class="muted">在线 Agent</div><strong>{{ data.server_online || 0 }}/{{ data.server_total || 0 }}</strong></div>
    </div>
    <div class="page-card" style="margin-top:16px">
      <div class="page-title">最近失败任务</div>
      <el-table :data="data.recent_failed || []">
        <el-table-column prop="run_no" label="运行编号" min-width="210" />
        <el-table-column prop="task_name" label="任务" min-width="180" />
        <el-table-column prop="status" label="状态" width="120" />
        <el-table-column prop="error_message" label="错误" min-width="280" show-overflow-tooltip />
        <el-table-column label="结束时间" width="190"><template #default="s">{{ $dt(s.row.finished_at) }}</template></el-table-column>
        <el-table-column label="操作" width="90"><template #default="s"><el-button link type="primary" @click="$router.push(`/runs/${s.row.run_id}`)">详情</el-button></template></el-table-column>
      </el-table>
    </div>
  </div>
</template>
<script setup>
import { onMounted, reactive, watch } from 'vue'
import api from '../api'
import { platformContext } from '../context'
const data = reactive({})
async function load(){ Object.assign(data, (await api.get('/dashboard/summary', { params: platformContext.projectId ? { project_id: platformContext.projectId } : {} })).data) }
onMounted(load); watch(() => platformContext.projectId, load)
</script>
<style scoped>
.metrics{display:grid;grid-template-columns:repeat(5,minmax(140px,1fr));gap:14px}.metric{background:#fff;border-radius:8px;padding:18px;box-shadow:0 1px 3px rgba(0,0,0,.08)}.metric strong{font-size:28px;display:block;margin-top:8px}
</style>

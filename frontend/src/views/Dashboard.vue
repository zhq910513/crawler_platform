<template>
  <div>
    <el-row :gutter="16">
      <el-col v-for="item in cards" :key="item.label" :span="4"><el-card shadow="never" class="stat-card"><div class="muted">{{ item.label }}</div><div class="number">{{ item.value }}</div></el-card></el-col>
    </el-row>
    <div class="page-card" style="margin-top:16px">
      <div class="page-title">最近失败任务</div>
      <el-table :data="data.recent_failed || []" empty-text="暂无失败任务">
        <el-table-column prop="task_name" label="任务名称" min-width="180" />
        <el-table-column prop="run_no" label="运行编号" min-width="220" />
        <el-table-column prop="status" label="状态" width="110" />
        <el-table-column prop="error_message" label="异常摘要" min-width="260" show-overflow-tooltip />
        <el-table-column prop="finished_at" label="结束时间" width="190" />
        <el-table-column label="操作" width="90"><template #default="scope"><el-button link type="primary" @click="$router.push(`/runs/${scope.row.run_id}`)">详情</el-button></template></el-table-column>
      </el-table>
    </div>
  </div>
</template>
<script setup>
import { computed, onMounted, reactive } from 'vue'
import api from '../api'
const data = reactive({})
const cards = computed(() => [
  { label:'任务总数', value:data.task_total || 0 }, { label:'运行中', value:data.running || 0 }, { label:'今日成功', value:data.success_today || 0 },
  { label:'今日失败', value:data.failed_today || 0 }, { label:'服务器在线', value:`${data.server_online || 0}/${data.server_total || 0}` }, { label:'离线服务器', value:Math.max(0,(data.server_total||0)-(data.server_online||0)) }
])
onMounted(async () => Object.assign(data, (await api.get('/dashboard/summary')).data))
</script>
<style scoped>.stat-card{height:110px}.number{font-size:30px;font-weight:700;margin-top:14px;color:#303133}</style>

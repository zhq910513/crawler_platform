<template>
  <div class="page-card">
    <div class="toolbar"><el-button type="primary" @click="load">刷新</el-button><span class="muted">Agent 每 15 秒上报，性能历史每分钟落库</span></div>
    <el-table :data="rows" v-loading="loading">
      <el-table-column prop="server_name" label="服务器" min-width="180" />
      <el-table-column prop="server_code" label="编码" min-width="170" />
      <el-table-column prop="server_ip" label="IP" width="150" />
      <el-table-column label="状态" width="110"><template #default="s"><span :class="['status-dot',s.row.status.toLowerCase()]"/>{{ s.row.status }}</template></el-table-column>
      <el-table-column label="CPU" width="130"><template #default="s"><el-progress :percentage="num(s.row.metric?.cpu_percent)" :stroke-width="10" /></template></el-table-column>
      <el-table-column label="内存" width="130"><template #default="s"><el-progress :percentage="num(s.row.metric?.memory_percent)" :stroke-width="10" /></template></el-table-column>
      <el-table-column label="磁盘" width="130"><template #default="s"><el-progress :percentage="num(s.row.metric?.disk_percent)" :stroke-width="10" /></template></el-table-column>
      <el-table-column label="任务槽位" width="120"><template #default="s">{{ s.row.metric?.running_task_count || 0 }} / {{ s.row.max_container_slots }}</template></el-table-column>
      <el-table-column label="Docker" min-width="130"><template #default="s">{{ s.row.agent?.docker_version || '-' }}</template></el-table-column>
      <el-table-column label="最后心跳" width="190"><template #default="s">{{ $dt(s.row.agent?.last_heartbeat_at) }}</template></el-table-column>
      <el-table-column label="操作" width="100"><template #default="s"><el-button link type="primary" @click="showMetrics(s.row)">趋势</el-button></template></el-table-column>
    </el-table>
    <el-dialog v-model="chartVisible" :title="`${current?.server_name || ''} 性能趋势`" width="900px" @opened="renderChart"><div ref="chartRef" style="height:420px"></div></el-dialog>
  </div>
</template>
<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'; import * as echarts from 'echarts'; import api from '../api'
const rows=ref([]),loading=ref(false),chartVisible=ref(false),current=ref(null),metrics=ref([]),chartRef=ref(null);let chart=null
const num=v=>Math.round(Number(v||0)*10)/10
async function load(){loading.value=true;try{rows.value=(await api.get('/servers')).data}finally{loading.value=false}}
async function showMetrics(row){current.value=row;metrics.value=(await api.get(`/servers/${row.server_id}/metrics`,{params:{limit:300}})).data;chartVisible.value=true}
async function renderChart(){await nextTick();chart?.dispose();chart=echarts.init(chartRef.value);chart.setOption({tooltip:{trigger:'axis'},legend:{data:['CPU','内存','磁盘']},xAxis:{type:'category',data:metrics.value.map(x=>x.recorded_at)},yAxis:{type:'value',min:0,max:100},series:[{name:'CPU',type:'line',data:metrics.value.map(x=>x.cpu_percent),showSymbol:false},{name:'内存',type:'line',data:metrics.value.map(x=>x.memory_percent),showSymbol:false},{name:'磁盘',type:'line',data:metrics.value.map(x=>x.disk_percent),showSymbol:false}]})}
onMounted(load);onBeforeUnmount(()=>chart?.dispose())
</script>

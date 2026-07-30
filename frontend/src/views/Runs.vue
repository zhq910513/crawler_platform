<template>
  <div class="page-card">
    <div class="toolbar">
      <el-select v-model="query.status" clearable placeholder="运行状态" style="width:180px"><el-option v-for="s in statuses" :key="s" :label="s" :value="s"/></el-select>
      <el-button type="primary" @click="load">查询</el-button><el-button @click="reset">重置</el-button>
    </div>
    <el-table :data="rows" v-loading="loading">
      <el-table-column prop="run_no" label="运行编号" min-width="220" />
      <el-table-column prop="task_id" label="任务ID" width="90" />
      <el-table-column label="状态" width="150"><template #default="s"><el-tag :type="tagType(s.row.status)">{{ s.row.status }}</el-tag></template></el-table-column>
      <el-table-column label="尝试" width="90"><template #default="s">{{ s.row.attempt }}/{{ s.row.max_attempts }}</template></el-table-column>
      <el-table-column prop="server_id" label="Agent服务器" width="120" />
      <el-table-column label="开始时间" width="190"><template #default="s">{{ $dt(s.row.started_at || s.row.queued_at) }}</template></el-table-column>
      <el-table-column label="耗时" width="110"><template #default="s">{{ s.row.duration_ms ? `${Math.round(s.row.duration_ms/1000)}s` : '-' }}</template></el-table-column>
      <el-table-column label="最近错误" min-width="260" show-overflow-tooltip><template #default="s">{{ s.row.last_error?.message || '-' }}</template></el-table-column>
      <el-table-column label="操作" width="170" fixed="right"><template #default="s"><el-button link type="primary" @click="$router.push(`/runs/${s.row.run_id}`)">详情</el-button><el-button v-if="['FAILED','TIMED_OUT','LOST'].includes(s.row.status)" link type="warning" @click="retry(s.row)">重试</el-button></template></el-table-column>
    </el-table>
    <div style="display:flex;justify-content:flex-end;margin-top:16px"><el-pagination v-model:current-page="query.page" v-model:page-size="query.page_size" :total="total" layout="total, sizes, prev, pager, next" @change="load" /></div>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref, watch } from 'vue';import { useRoute } from 'vue-router';import { ElMessage } from 'element-plus';import api from '../api';import { platformContext } from '../context'
const route=useRoute(),rows=ref([]),total=ref(0),loading=ref(false);const statuses=['CREATED','QUEUED','ASSIGNED','STARTING','RUNNING','CANCEL_REQUESTED','SUCCEEDED','PARTIAL_SUCCESS','SKIPPED','FAILED','CANCELLED','TIMED_OUT','LOST'];const query=reactive({status:'',page:1,page_size:20})
function tagType(v){return ({SUCCEEDED:'success',PARTIAL_SUCCESS:'warning',FAILED:'danger',TIMED_OUT:'danger',LOST:'danger',RUNNING:'primary',STARTING:'warning',ASSIGNED:'warning',QUEUED:'info',CANCEL_REQUESTED:'warning',CANCELLED:'info',SKIPPED:'info'})[v]||'info'}
async function load(){loading.value=true;try{const params={...query};if(route.query.task_id)params.task_id=route.query.task_id;if(platformContext.projectId)params.project_id=platformContext.projectId;const {data}=await api.get('/runs',{params});rows.value=data.items;total.value=data.total}catch(e){ElMessage.error(e.response?.data?.detail||'加载失败')}finally{loading.value=false}}
function reset(){query.status='';query.page=1;load()}async function retry(row){try{const {data}=await api.post(`/runs/${row.run_id}/retry`);ElMessage.success(`已创建重试：${data.run_no}`);load()}catch(e){ElMessage.error(e.response?.data?.detail||'重试失败')}}
onMounted(load);watch(()=>platformContext.projectId,load)
</script>

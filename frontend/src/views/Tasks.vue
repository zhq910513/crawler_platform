<template>
  <div class="page-card">
    <div class="toolbar">
      <el-input v-model="query.keyword" placeholder="名称 / 编码 / 入口" clearable style="width:280px" @keyup.enter="load" />
      <el-select v-model="query.status" clearable placeholder="状态" style="width:130px"><el-option label="启用" value="ENABLED"/><el-option label="停用" value="DISABLED"/></el-select>
      <el-button type="primary" @click="load">查询</el-button><el-button @click="reset">重置</el-button>
      <el-button v-if="canManageProject" type="success" :disabled="!platformContext.projectId" @click="$router.push('/tasks/new')">新增任务</el-button>
    </div>
    <el-table :data="rows" v-loading="loading">
      <el-table-column prop="task_name" label="任务名称" min-width="170" />
      <el-table-column prop="task_code" label="任务编码" min-width="170" />
      <el-table-column prop="spider_task_name" label="SpiderEntry" min-width="190" />
      <el-table-column label="调度" min-width="180"><template #default="s"><span>{{ s.row.schedule?.cron_expression || '仅手动' }}</span><div class="muted">{{ $dt(s.row.schedule?.next_run_at) }}</div></template></el-table-column>
      <el-table-column label="最近状态" width="150"><template #default="s"><el-tag :type="tagType(s.row.latest_run?.status)">{{ s.row.latest_run?.status || '未运行' }}</el-tag><div class="muted truncate">{{ s.row.latest_run?.last_error_message }}</div></template></el-table-column>
      <el-table-column prop="status" label="任务状态" width="100" />
      <el-table-column label="操作" width="300" fixed="right"><template #default="s">
        <el-button v-if="['OWNER','OPERATOR'].includes(s.row.project_role)" link type="primary" @click="runNow(s.row)">执行</el-button>
        <el-button link @click="$router.push(`/runs?task_id=${s.row.task_id}`)">记录</el-button>
        <el-button v-if="s.row.latest_run" link @click="$router.push(`/runs/${s.row.latest_run.run_id}`)">日志</el-button>
        <el-button v-if="s.row.project_role==='OWNER'" link type="warning" @click="$router.push(`/tasks/${s.row.task_id}/edit`)">编辑</el-button>
        <el-button v-if="s.row.project_role==='OWNER'" link type="danger" @click="remove(s.row)">删除</el-button>
      </template></el-table-column>
    </el-table>
    <div style="display:flex;justify-content:flex-end;margin-top:16px"><el-pagination v-model:current-page="query.page" v-model:page-size="query.page_size" :total="total" layout="total, sizes, prev, pager, next" @change="load" /></div>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { canManageProject, platformContext } from '../context'
const rows=ref([]),total=ref(0),loading=ref(false);const query=reactive({keyword:'',status:'',page:1,page_size:20})
function tagType(v){return ({SUCCEEDED:'success',PARTIAL_SUCCESS:'warning',FAILED:'danger',TIMED_OUT:'danger',LOST:'danger',RUNNING:'primary',STARTING:'warning',ASSIGNED:'warning',QUEUED:'info',CANCELLED:'info',SKIPPED:'info'})[v]||'info'}
async function load(){loading.value=true;try{const params={...query};if(platformContext.projectId)params.project_id=platformContext.projectId;const {data}=await api.get('/tasks',{params});rows.value=data.items;total.value=data.total}catch(e){ElMessage.error(e.response?.data?.detail||'加载失败')}finally{loading.value=false}}
function reset(){Object.assign(query,{keyword:'',status:'',page:1,page_size:20});load()}
async function runNow(row){try{const {data}=await api.post(`/tasks/${row.task_id}/run`);ElMessage.success(`已创建：${data.run_no}`);load()}catch(e){ElMessage.error(e.response?.data?.detail||'执行失败')}}
async function remove(row){try{await ElMessageBox.confirm(`确认删除“${row.task_name}”？`,'提示',{type:'warning'});await api.delete(`/tasks/${row.task_id}`);ElMessage.success('已删除');load()}catch(e){if(e!=='cancel')ElMessage.error(e.response?.data?.detail||'删除失败')}}
onMounted(load);watch(()=>platformContext.projectId,()=>{query.page=1;load()})
</script>

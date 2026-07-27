<template>
  <div class="page-card">
    <div class="toolbar">
      <el-input v-model="query.keyword" placeholder="任务名称 / 编码 / 平台" clearable style="width:280px" @keyup.enter="load" />
      <el-select v-model="query.status" clearable placeholder="任务状态" style="width:140px"><el-option label="正常" value="ENABLED"/><el-option label="停用" value="DISABLED"/></el-select>
      <el-button type="primary" @click="load">查询</el-button>
      <el-button @click="reset">重置</el-button>
      <el-button v-if="isAdmin" type="success" @click="$router.push('/tasks/new')">新增任务</el-button>
    </div>
    <el-table :data="rows" v-loading="loading">
      <el-table-column prop="task_id" label="ID" width="70" />
      <el-table-column prop="task_name" label="任务名称" min-width="190" show-overflow-tooltip />
      <el-table-column prop="task_code" label="任务编码" min-width="180" show-overflow-tooltip />
      <el-table-column prop="platform" label="平台" width="120" />
      <el-table-column prop="task_group" label="分组" width="120" />
      <el-table-column label="调度" min-width="170"><template #default="s"><span>{{ s.row.schedule?.cron_expression || '仅手动' }}</span><div class="muted">{{ $dt(s.row.schedule?.next_run_at) }}</div></template></el-table-column>
      <el-table-column label="最近状态" width="120"><template #default="s"><el-tag :type="tagType(s.row.latest_run?.status)">{{ s.row.latest_run?.status || '未运行' }}</el-tag></template></el-table-column>
      <el-table-column label="任务状态" width="95"><template #default="s"><el-tag :type="s.row.status==='ENABLED'?'success':'info'">{{ s.row.status==='ENABLED'?'正常':'停用' }}</el-tag></template></el-table-column>
      <el-table-column prop="developer" label="负责人" width="110" />
      <el-table-column label="操作" width="330" fixed="right">
        <template #default="s">
          <el-button link type="primary" @click="runNow(s.row)">立即执行</el-button>
          <el-button link type="primary" @click="openSchedule(s.row)">调度时间</el-button>
          <el-button link @click="$router.push(`/runs?task_id=${s.row.task_id}`)">记录</el-button>
          <el-button v-if="s.row.latest_run" link @click="$router.push(`/runs/${s.row.latest_run.run_id}`)">日志</el-button>
          <template v-if="isAdmin">
            <el-button link type="warning" @click="$router.push(`/tasks/${s.row.task_id}/edit`)">编辑</el-button>
            <el-button link type="danger" @click="remove(s.row)">删除</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>
    <div style="display:flex;justify-content:flex-end;margin-top:16px"><el-pagination v-model:current-page="query.page" v-model:page-size="query.page_size" :total="total" layout="total, sizes, prev, pager, next" @change="load" /></div>

    <el-dialog v-model="scheduleVisible" title="修改调度时间" width="560px">
      <el-form label-width="120px">
        <el-form-item label="Cron 表达式"><el-input v-model="schedule.cron_expression" /></el-form-item>
        <el-form-item label="时区"><el-input v-model="schedule.timezone" /></el-form-item>
        <el-form-item label="错过计划策略"><el-select v-model="schedule.misfire_policy"><el-option label="立即补跑" value="FIRE_NOW"/><el-option label="合并补跑一次" value="FIRE_ONCE"/><el-option label="放弃" value="SKIP"/></el-select></el-form-item>
        <el-form-item label="启用调度"><el-switch v-model="schedule.enabled" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="scheduleVisible=false">取消</el-button><el-button type="primary" @click="saveSchedule">保存</el-button></template>
    </el-dialog>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { isAdmin } from '../auth'
const rows=ref([]), total=ref(0), loading=ref(false), scheduleVisible=ref(false), currentTask=ref(null)
const query=reactive({keyword:'',status:'',page:1,page_size:20})
const schedule=reactive({cron_expression:'',timezone:'Asia/Shanghai',misfire_policy:'FIRE_ONCE',enabled:true})
function tagType(v){ return ({SUCCESS:'success',FAILED:'danger',TIMEOUT:'danger',LOST:'danger',RUNNING:'primary',CLAIMED:'warning',QUEUED:'info',CANCELLED:'info',SKIPPED:'info'})[v]||'info' }
async function load(){loading.value=true;try{const {data}=await api.get('/tasks',{params:query});rows.value=data.items;total.value=data.total}catch(e){ElMessage.error(e.response?.data?.detail||'加载失败')}finally{loading.value=false}}
function reset(){Object.assign(query,{keyword:'',status:'',page:1,page_size:20});load()}
async function runNow(row){try{const {data}=await api.post(`/tasks/${row.task_id}/run`);ElMessage.success(`已创建运行实例：${data.run_no}`);load()}catch(e){ElMessage.error(e.response?.data?.detail||'执行失败')}}
function openSchedule(row){currentTask.value=row;Object.assign(schedule,{cron_expression:row.schedule?.cron_expression||'',timezone:row.schedule?.timezone||'Asia/Shanghai',misfire_policy:row.schedule?.misfire_policy||'FIRE_ONCE',enabled:!!row.schedule?.enabled});scheduleVisible.value=true}
async function saveSchedule(){try{await api.patch(`/tasks/${currentTask.value.task_id}/schedule`,schedule);ElMessage.success('调度已更新');scheduleVisible.value=false;load()}catch(e){ElMessage.error(e.response?.data?.detail||'保存失败')}}
async function remove(row){try{await ElMessageBox.confirm(`确认删除任务“${row.task_name}”？`,'提示',{type:'warning'});await api.delete(`/tasks/${row.task_id}`);ElMessage.success('已删除');load()}catch(e){if(e!=='cancel')ElMessage.error(e.response?.data?.detail||'删除失败')}}
onMounted(load)
</script>

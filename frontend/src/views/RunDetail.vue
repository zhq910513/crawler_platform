<template>
  <div>
    <div class="page-card">
      <div class="toolbar"><el-button @click="$router.back()">返回</el-button><el-button v-if="isAdmin && active" type="danger" @click="cancel">终止任务</el-button><el-button @click="load">刷新</el-button></div>
      <el-descriptions :column="3" border v-if="run.run_id">
        <el-descriptions-item label="任务名称">{{ run.task_name }}</el-descriptions-item><el-descriptions-item label="运行编号">{{ run.run_no }}</el-descriptions-item><el-descriptions-item label="状态"><el-tag>{{ run.status }}</el-tag></el-descriptions-item>
        <el-descriptions-item label="服务器">{{ run.server_id }}</el-descriptions-item><el-descriptions-item label="容器名称">{{ run.container_name || '-' }}</el-descriptions-item><el-descriptions-item label="退出码">{{ run.exit_code ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="镜像" :span="2">{{ run.image_name }}:{{ run.image_tag }}</el-descriptions-item><el-descriptions-item label="Commit">{{ run.git_commit || '-' }}</el-descriptions-item>
        <el-descriptions-item label="开始时间">{{ $dt(run.started_at) }}</el-descriptions-item><el-descriptions-item label="结束时间">{{ $dt(run.finished_at) }}</el-descriptions-item><el-descriptions-item label="最后日志">{{ $dt(run.last_log_at) }}</el-descriptions-item>
        <el-descriptions-item label="异常" :span="3">{{ run.error_type }} {{ run.error_message }}</el-descriptions-item>
      </el-descriptions>
    </div>
    <div class="page-card" style="margin-top:16px"><div class="page-title">程序日志 <span class="muted">（运行中每 2 秒刷新）</span></div><div ref="logBox" class="code-block">{{ logs || '暂无日志' }}</div></div>
    <div class="page-card" style="margin-top:16px"><div class="page-title">容器事件</div><el-table :data="run.events||[]"><el-table-column label="时间" width="190"><template #default="s">{{ $dt(s.row.occurred_at) }}</template></el-table-column><el-table-column prop="event_type" label="类型" width="120"/><el-table-column prop="event_action" label="动作" width="140"/><el-table-column prop="event_message" label="信息" min-width="260"/></el-table></div>
  </div>
</template>
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'; import { useRoute } from 'vue-router'; import { ElMessage, ElMessageBox } from 'element-plus'; import api from '../api'; import { isAdmin } from '../auth'
const route=useRoute(),run=reactive({}),logs=ref(''),logBox=ref(null);let timer=null
const active=computed(()=>['QUEUED','CLAIMED','STARTING','RUNNING','RETRY_WAIT'].includes(run.status))
async function load(){Object.assign(run,(await api.get(`/runs/${route.params.id}`)).data);logs.value=(await api.get(`/runs/${route.params.id}/logs`,{responseType:'text'})).data;await nextTick();if(logBox.value)logBox.value.scrollTop=logBox.value.scrollHeight}
async function cancel(){try{await ElMessageBox.confirm('确认终止该运行实例？','提示',{type:'warning'});await api.post(`/runs/${run.run_id}/cancel`);ElMessage.success('停止指令已下发');load()}catch(e){if(e!=='cancel')ElMessage.error(e.response?.data?.detail||'操作失败')}}
onMounted(async()=>{await load();timer=setInterval(()=>{if(active.value)load()},2000)});onBeforeUnmount(()=>clearInterval(timer))
</script>

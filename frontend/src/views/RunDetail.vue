<template>
  <div>
    <div class="page-card">
      <div class="toolbar"><el-button @click="$router.back()">返回</el-button><el-button v-if="active" type="danger" @click="cancel">终止任务</el-button><el-button v-if="['FAILED','TIMED_OUT','LOST'].includes(run.status)" type="warning" @click="retry">重试</el-button><el-button @click="load">刷新</el-button><span class="muted">事件流：{{ eventConnected?'已连接':'重连中' }}　日志流：{{ logConnected?'已连接':'重连中' }}</span></div>
      <el-descriptions :column="3" border v-if="run.run_id">
        <el-descriptions-item label="运行编号">{{ run.run_no }}</el-descriptions-item><el-descriptions-item label="状态"><el-tag>{{ run.status }}</el-tag></el-descriptions-item><el-descriptions-item label="尝试">{{ run.attempt }}/{{ run.max_attempts }}</el-descriptions-item>
        <el-descriptions-item label="Agent">{{ run.agent_id || '-' }}</el-descriptions-item><el-descriptions-item label="容器">{{ run.container_name || '-' }}</el-descriptions-item><el-descriptions-item label="退出码">{{ run.exit_code ?? '-' }} <span v-if="run.oom_killed">/ OOM</span></el-descriptions-item>
        <el-descriptions-item label="镜像" :span="2">{{ run.image_name }}@{{ run.image_digest }}</el-descriptions-item><el-descriptions-item label="Commit">{{ run.git_commit || '-' }}</el-descriptions-item>
        <el-descriptions-item label="开始">{{ $dt(run.started_at) }}</el-descriptions-item><el-descriptions-item label="结束">{{ $dt(run.finished_at) }}</el-descriptions-item><el-descriptions-item label="耗时">{{ run.duration_ms ? `${Math.round(run.duration_ms/1000)}s` : '-' }}</el-descriptions-item>
      </el-descriptions>
      <el-alert v-if="run.last_error" style="margin-top:14px" type="warning" :closable="false" :title="`最近错误：${run.last_error.message}`" :description="`${run.last_error.code || '-'} / ${run.last_error.type || '-'} / ${$dt(run.last_error.occurred_at)}`" />
      <el-alert v-if="run.terminal_error" style="margin-top:10px" type="error" :closable="false" :title="`最终失败：${run.terminal_error.message}`" :description="`${run.terminal_error.code || '-'} / ${run.terminal_error.type || '-'}`" />
    </div>
    <div class="page-card" style="margin-top:16px"><div class="page-title">实时程序日志</div><div ref="logBox" class="code-block">{{ logs || '暂无日志' }}</div></div>
    <div class="page-card" style="margin-top:16px"><div class="page-title">ERROR / CRITICAL</div><el-table :data="errors"><el-table-column label="时间" width="190"><template #default="s">{{ $dt(s.row.occurred_at) }}</template></el-table-column><el-table-column prop="level" label="级别" width="90"/><el-table-column prop="event_name" label="事件" width="180"/><el-table-column prop="error_code" label="错误码" min-width="190"/><el-table-column prop="message" label="消息" min-width="280" show-overflow-tooltip/></el-table></div>
    <div class="page-card" style="margin-top:16px"><div class="page-title">指标与结果</div><pre class="json-block">{{ JSON.stringify({metrics:run.metrics,result:run.result},null,2) }}</pre></div>
  </div>
</template>
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue';import { useRoute } from 'vue-router';import { ElMessage, ElMessageBox } from 'element-plus';import api,{streamSSE} from '../api'
const route=useRoute(),run=reactive({}),logs=ref(''),errors=ref([]),logBox=ref(null),eventConnected=ref(false),logConnected=ref(false);let eventAbort,logAbort,eventCursor=0,logOffset=0
const active=computed(()=>['CREATED','QUEUED','ASSIGNED','STARTING','RUNNING','CANCEL_REQUESTED'].includes(run.status))
async function load(){const {data}=await api.get(`/runs/${route.params.id}`);Object.assign(run,data);errors.value=data.recent_errors||[];eventCursor=errors.value.reduce((m,x)=>Math.max(m,x.event_id||0),eventCursor);const log=(await api.get(`/runs/${route.params.id}/logs`)).data;logs.value=log.content||'';logOffset=log.offset||0;scrollBottom()}
function appendLog(line){logs.value+=(logs.value?'\n':'')+line;if(logs.value.length>1_500_000)logs.value=logs.value.slice(-1_200_000);scrollBottom()}
async function scrollBottom(){await nextTick();if(logBox.value)logBox.value.scrollTop=logBox.value.scrollHeight}
function startStreams(){eventAbort?.abort();logAbort?.abort();eventAbort=new AbortController();logAbort=new AbortController();connectEvents(1000);connectLogs(1000)}
async function connectEvents(delay){try{await streamSSE(`/runs/${run.run_id}/events/stream?after_event_id=${eventCursor}`,{signal:eventAbort.signal,onOpen:()=>eventConnected.value=true,onEvent:({event,id,data})=>{if(id)eventCursor=Math.max(eventCursor,Number(id));if(event==='run_snapshot')Object.assign(run,data);if(event==='run_event'){errors.value.push(data);if(errors.value.length>100)errors.value.shift()}if(event==='stream_closed'){eventConnected.value=false;logConnected.value=false;eventAbort.abort();logAbort?.abort()}}})}catch(e){if(!eventAbort.signal.aborted){eventConnected.value=false;setTimeout(()=>connectEvents(Math.min(delay*2,10000)),delay)}}}
async function connectLogs(delay){try{await streamSSE(`/runs/${run.run_id}/logs/stream?offset=${logOffset}`,{signal:logAbort.signal,onOpen:()=>logConnected.value=true,onEvent:({event,data})=>{if(event==='log'){logOffset=data.offset;appendLog(data.line)}}})}catch(e){if(!logAbort.signal.aborted){logConnected.value=false;setTimeout(()=>connectLogs(Math.min(delay*2,10000)),delay)}}}
async function cancel(){try{await ElMessageBox.confirm('确认终止该运行实例？','提示',{type:'warning'});await api.post(`/runs/${run.run_id}/cancel`);ElMessage.success('停止指令已下发')}catch(e){if(e!=='cancel')ElMessage.error(e.response?.data?.detail||'操作失败')}}async function retry(){try{const {data}=await api.post(`/runs/${run.run_id}/retry`);ElMessage.success(`已创建重试：${data.run_no}`)}catch(e){ElMessage.error(e.response?.data?.detail||'重试失败')}}
onMounted(async()=>{await load();startStreams()});onBeforeUnmount(()=>{eventAbort?.abort();logAbort?.abort()})
</script>

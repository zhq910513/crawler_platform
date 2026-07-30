<template>
  <div class="page-card">
    <div class="page-title">{{ editing ? '编辑任务' : '新增任务' }}</div>
    <el-alert v-if="!projectId" type="warning" :closable="false" title="请先在顶部选择项目" />
    <el-form v-else label-width="150px" style="max-width:900px">
      <el-form-item label="任务名称"><el-input v-model="form.task_name" /></el-form-item>
      <el-form-item label="任务编码"><el-input v-model="form.task_code" /></el-form-item>
      <el-form-item label="发布策略"><el-radio-group v-model="form.runtime.image_policy" @change="refreshEntries"><el-radio value="RELEASE_CHANNEL">项目通道</el-radio><el-radio value="PINNED">固定版本</el-radio></el-radio-group></el-form-item>
      <el-form-item v-if="form.runtime.image_policy==='RELEASE_CHANNEL'" label="发布通道"><el-select v-model="form.runtime.release_channel" style="width:360px" @change="refreshEntries"><el-option v-for="x in channels" :key="x.channel_name" :label="`${x.channel_name} / ${x.version||'未绑定'}`" :value="x.channel_name"/></el-select></el-form-item>
      <el-form-item v-else label="固定版本"><el-select v-model="form.runtime.fixed_spider_release_id" style="width:500px" @change="refreshEntries"><el-option v-for="x in releases" :key="x.release_id" :label="`${x.version} / ${x.image_digest}`" :value="x.release_id"/></el-select></el-form-item>
      <el-form-item label="爬虫入口"><el-select v-model="form.spider_task_name" style="width:500px"><el-option v-for="x in entries" :key="x.task_name" :label="`${x.display_name || x.task_name} (${x.task_name})`" :value="x.task_name"/></el-select><div v-if="selectedEntry" class="muted block">类型：{{ selectedEntry.image_profile }}，默认超时：{{ selectedEntry.default_timeout_seconds }} 秒，需要资源：{{ selectedEntry.required_resources?.join(', ') || '无' }}</div></el-form-item>
      <el-form-item label="任务参数 JSON"><el-input v-model="parametersText" type="textarea" :rows="8" /></el-form-item>
      <el-form-item label="Agent 服务器"><el-select v-model="form.server_ids" multiple style="width:600px"><el-option v-for="x in servers" :key="x.server_id" :label="`${x.server_name} / ${x.status}`" :value="x.server_id"/></el-select></el-form-item>
      <el-form-item label="CPU / 内存"><el-input-number v-model="form.runtime.cpu_limit" :min="0.1" :max="128" :step="0.5" /> <span style="margin:0 8px">核</span><el-input-number v-model="form.runtime.memory_limit_mb" :min="128" :max="1048576" :step="256" /> <span style="margin-left:8px">MB</span></el-form-item>
      <el-form-item label="调度方式"><el-radio-group v-model="form.schedule.schedule_type"><el-radio value="MANUAL">仅手动</el-radio><el-radio value="CRON">Cron</el-radio></el-radio-group></el-form-item>
      <template v-if="form.schedule.schedule_type==='CRON'"><el-form-item label="Cron 表达式"><el-input v-model="form.schedule.cron_expression" /></el-form-item><el-form-item label="时区"><el-input v-model="form.schedule.timezone" /></el-form-item><el-form-item label="启用调度"><el-switch v-model="form.schedule.enabled" /></el-form-item></template>
      <el-form-item label="超时 / 重试"><el-input-number v-model="form.schedule.timeout_seconds" :min="1" :max="604800" /><span style="margin:0 12px">秒</span><el-input-number v-model="form.schedule.max_retry_count" :min="0" :max="20" /><span style="margin-left:8px">次重试</span></el-form-item>
      <el-form-item label="状态"><el-select v-model="form.status"><el-option label="启用" value="ENABLED"/><el-option label="停用" value="DISABLED"/></el-select></el-form-item>
      <el-form-item label="说明"><el-input v-model="form.description" type="textarea" /></el-form-item>
      <el-form-item><el-button type="primary" @click="save">保存</el-button><el-button @click="$router.back()">取消</el-button></el-form-item>
    </el-form>
  </div>
</template>
<script setup>
import { computed, onMounted, reactive, ref } from 'vue';import { useRoute,useRouter } from 'vue-router';import { ElMessage } from 'element-plus';import api from '../api';import { platformContext } from '../context'
const route=useRoute(),router=useRouter(),editing=computed(()=>!!route.params.id),projectId=computed(()=>editing.value?form.project_id:platformContext.projectId),releases=ref([]),channels=ref([]),entries=ref([]),servers=ref([]),parametersText=ref('{}')
const form=reactive({task_code:'',task_name:'',project_id:null,spider_task_name:'',platform:'',task_group:'default',developer:'',parameters:{},status:'ENABLED',description:'',runtime:{image_policy:'RELEASE_CHANNEL',fixed_spider_release_id:null,release_channel:'stable',pull_policy:'IF_NOT_PRESENT',cpu_limit:2,memory_limit_mb:4096,shm_size_mb:256,pids_limit:512,stop_grace_seconds:30,auto_remove:true,keep_failed_container:false},schedule:{schedule_type:'MANUAL',cron_expression:'',timezone:'Asia/Shanghai',misfire_policy:'FIRE_ONCE',max_concurrency:1,overlap_policy:'SKIP',timeout_seconds:3600,max_retry_count:0,retry_interval_seconds:60,retry_backoff:'FIXED',enabled:false},server_ids:[]})
const selectedEntry=computed(()=>entries.value.find(x=>x.task_name===form.spider_task_name))
async function loadRelease(id){if(!id){entries.value=[];return}const {data}=await api.get(`/spider-releases/${id}`);entries.value=data.entries||[];if(!entries.value.some(x=>x.task_name===form.spider_task_name))form.spider_task_name=entries.value[0]?.task_name||''}
async function refreshEntries(){if(form.runtime.image_policy==='PINNED')return loadRelease(form.runtime.fixed_spider_release_id);const channel=channels.value.find(x=>x.channel_name===form.runtime.release_channel);return loadRelease(channel?.spider_release_id)}
async function save(){try{form.project_id=projectId.value;form.parameters=JSON.parse(parametersText.value||'{}');const payload=JSON.parse(JSON.stringify(form));if(editing.value)await api.put(`/tasks/${route.params.id}`,payload);else await api.post('/tasks',payload);ElMessage.success('保存成功');router.push('/tasks')}catch(e){ElMessage.error(e instanceof SyntaxError?'任务参数不是有效 JSON':(e.response?.data?.detail||'保存失败'))}}
onMounted(async()=>{releases.value=(await api.get('/spider-releases')).data;servers.value=(await api.get('/servers')).data;if(editing.value){const {data}=await api.get(`/tasks/${route.params.id}`);Object.assign(form,data);parametersText.value=JSON.stringify(data.parameters||{},null,2)}else form.project_id=platformContext.projectId;if(form.project_id)channels.value=(await api.get(`/projects/${form.project_id}/channels`)).data;if(form.runtime.image_policy==='PINNED'&&!form.runtime.fixed_spider_release_id)form.runtime.fixed_spider_release_id=releases.value[0]?.release_id||null;await refreshEntries()})
</script>

<template>
  <div class="page-card">
    <div class="page-title">{{ editing ? '编辑爬虫任务' : '新增爬虫任务' }}</div>
    <el-tabs v-model="activeTab">
      <el-tab-pane label="基础信息" name="base">
        <el-form :model="form" label-width="130px" style="max-width:900px">
          <el-form-item label="任务名称" required><el-input v-model="form.task_name" /></el-form-item>
          <el-form-item label="任务编码" required><el-input v-model="form.task_code" /></el-form-item>
          <el-form-item label="爬虫项目" required><el-select v-model="form.project_id" filterable style="width:100%" @change="loadImages"><el-option v-for="p in projects" :key="p.project_id" :label="p.project_name" :value="p.project_id"/></el-select></el-form-item>
          <el-form-item label="任务平台"><el-input v-model="form.platform" /></el-form-item>
          <el-form-item label="任务分组"><el-input v-model="form.task_group" /></el-form-item>
          <el-form-item label="负责人"><el-input v-model="form.developer" /></el-form-item>
          <el-form-item label="执行服务器" required><el-select v-model="form.server_ids" multiple style="width:100%"><el-option v-for="s in servers" :key="s.server_id" :label="`${s.server_name} (${s.status})`" :value="s.server_id"/></el-select></el-form-item>
          <el-form-item label="任务状态"><el-radio-group v-model="form.status"><el-radio value="ENABLED">正常</el-radio><el-radio value="DISABLED">停用</el-radio></el-radio-group></el-form-item>
          <el-form-item label="说明"><el-input v-model="form.description" type="textarea" :rows="3" /></el-form-item>
        </el-form>
      </el-tab-pane>
      <el-tab-pane label="镜像与执行" name="runtime">
        <el-form label-width="150px" style="max-width:1000px">
          <el-form-item label="镜像版本策略"><el-select v-model="form.runtime.image_policy"><el-option label="固定版本" value="PINNED"/><el-option label="发布通道" value="RELEASE_CHANNEL"/><el-option label="最新成功构建" value="LATEST_SUCCESSFUL"/></el-select></el-form-item>
          <el-form-item v-if="form.runtime.image_policy==='PINNED'" label="固定镜像版本" required><el-select v-model="form.runtime.fixed_image_version_id" filterable style="width:100%"><el-option v-for="i in images" :key="i.image_version_id" :label="`${i.image_tag} / ${i.git_commit || '-'} / ${i.image_digest.slice(0,20)}...`" :value="i.image_version_id"/></el-select></el-form-item>
          <el-form-item v-if="form.runtime.image_policy==='RELEASE_CHANNEL'" label="发布通道"><el-input v-model="form.runtime.release_channel" /></el-form-item>
          <el-form-item label="拉取策略"><el-select v-model="form.runtime.pull_policy"><el-option label="本地没有时拉取" value="IF_NOT_PRESENT"/><el-option label="每次拉取" value="ALWAYS"/><el-option label="禁止拉取" value="NEVER"/></el-select></el-form-item>
          <el-form-item label="执行方式"><el-select v-model="form.executor_type"><el-option label="Python 方法" value="PYTHON_METHOD"/><el-option label="Python 模块" value="PYTHON_MODULE"/><el-option label="自定义命令" value="COMMAND"/></el-select></el-form-item>
          <el-form-item v-if="form.executor_type!=='COMMAND'" label="业务入口" required><el-input v-model="form.entrypoint" placeholder="package.module:function" /></el-form-item>
          <el-form-item v-else label="容器命令 JSON"><el-input v-model="json.container_command" type="textarea" :rows="3" placeholder='["python","spider.py"]' /></el-form-item>
          <el-form-item label="位置参数 JSON"><el-input v-model="json.arguments" type="textarea" :rows="3" placeholder='[]' /></el-form-item>
          <el-form-item label="关键字参数 JSON"><el-input v-model="json.keyword_arguments" type="textarea" :rows="4" placeholder='{"site":"HK"}' /></el-form-item>
          <el-form-item label="环境变量 JSON"><el-input v-model="json.environment_variables" type="textarea" :rows="4" placeholder='{"APP_ENV":"production"}' /></el-form-item>
          <el-form-item label="密钥引用 JSON"><el-input v-model="json.secret_refs" type="textarea" :rows="4" placeholder='{"MYSQL_PWD":"business_mysql_pwd"}' /></el-form-item>
          <el-form-item label="挂载配置 JSON"><el-input v-model="json.volume_mounts" type="textarea" :rows="4" placeholder='[{"source":"/data/shared","target":"/app/shared","mode":"rw"}]' /></el-form-item>
          <el-form-item label="关联数据表 JSON"><el-input v-model="json.related_tables" type="textarea" :rows="3" placeholder='["wms_inventory"]' /></el-form-item>
          <el-form-item label="容器工作目录"><el-input v-model="form.runtime.container_working_dir" /></el-form-item>
          <el-form-item label="Docker 网络"><el-input v-model="form.runtime.network_mode" /></el-form-item>
        </el-form>
      </el-tab-pane>
      <el-tab-pane label="资源与调度" name="schedule">
        <el-form label-width="150px" style="max-width:900px">
          <el-divider content-position="left">资源限制</el-divider>
          <el-form-item label="CPU 限制"><el-input-number v-model="form.runtime.cpu_limit" :min="0.1" :max="64" :step="0.5" /></el-form-item>
          <el-form-item label="内存 MB"><el-input-number v-model="form.runtime.memory_limit_mb" :min="128" :max="262144" :step="256" /></el-form-item>
          <el-form-item label="共享内存 MB"><el-input-number v-model="form.runtime.shm_size_mb" :min="64" :max="65536" :step="64" /></el-form-item>
          <el-form-item label="最大进程数"><el-input-number v-model="form.runtime.pids_limit" :min="16" :max="32768" /></el-form-item>
          <el-divider content-position="left">调度策略</el-divider>
          <el-form-item label="调度类型"><el-radio-group v-model="form.schedule.schedule_type"><el-radio value="CRON">Cron</el-radio><el-radio value="MANUAL">仅手动</el-radio></el-radio-group></el-form-item>
          <el-form-item v-if="form.schedule.schedule_type==='CRON'" label="Cron 表达式"><el-input v-model="form.schedule.cron_expression" /></el-form-item>
          <el-form-item label="时区"><el-input v-model="form.schedule.timezone" /></el-form-item>
          <el-form-item label="错过计划策略"><el-select v-model="form.schedule.misfire_policy"><el-option label="立即补跑" value="FIRE_NOW"/><el-option label="合并补跑一次" value="FIRE_ONCE"/><el-option label="放弃" value="SKIP"/></el-select></el-form-item>
          <el-form-item label="最大并发"><el-input-number v-model="form.schedule.max_concurrency" :min="1" :max="100" /></el-form-item>
          <el-form-item label="重叠策略"><el-select v-model="form.schedule.overlap_policy"><el-option label="跳过" value="SKIP"/><el-option label="排队" value="QUEUE"/><el-option label="允许并发" value="ALLOW"/><el-option label="停止旧任务" value="REPLACE"/></el-select></el-form-item>
          <el-form-item label="超时秒数"><el-input-number v-model="form.schedule.timeout_seconds" :min="0" :max="604800" /></el-form-item>
          <el-form-item label="失败重试次数"><el-input-number v-model="form.schedule.max_retry_count" :min="0" :max="20" /></el-form-item>
          <el-form-item label="重试间隔秒"><el-input-number v-model="form.schedule.retry_interval_seconds" :min="1" :max="86400" /></el-form-item>
          <el-form-item label="重试退避"><el-select v-model="form.schedule.retry_backoff"><el-option label="固定间隔" value="FIXED"/><el-option label="指数退避" value="EXPONENTIAL"/></el-select></el-form-item>
          <el-form-item label="启用调度"><el-switch v-model="form.schedule.enabled" /></el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>
    <div style="margin-top:20px"><el-button @click="$router.back()">返回</el-button><el-button type="primary" :loading="saving" @click="save">保存任务</el-button></div>
  </div>
</template>
<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api'
const route=useRoute(), router=useRouter(), editing=computed(()=>!!route.params.id), activeTab=ref('base'), saving=ref(false), projects=ref([]), servers=ref([]), images=ref([])
const form=reactive({task_code:'',task_name:'',project_id:null,platform:'',task_group:'default',developer:'',executor_type:'PYTHON_METHOD',entrypoint:'',status:'ENABLED',description:'',server_ids:[],runtime:{image_policy:'PINNED',fixed_image_version_id:null,release_channel:'stable',pull_policy:'IF_NOT_PRESENT',container_command:[],container_working_dir:'',environment_variables:{},secret_refs:{},volume_mounts:[],network_mode:'bridge',cpu_limit:2,memory_limit_mb:4096,shm_size_mb:256,pids_limit:512,stop_grace_seconds:30,auto_remove:true,keep_failed_container:false},schedule:{schedule_type:'CRON',cron_expression:'0 20 6 * * *',timezone:'Asia/Shanghai',misfire_policy:'FIRE_ONCE',max_concurrency:1,overlap_policy:'SKIP',timeout_seconds:3600,max_retry_count:0,retry_interval_seconds:60,retry_backoff:'FIXED',enabled:true}})
const json=reactive({arguments:'[]',keyword_arguments:'{}',container_command:'[]',environment_variables:'{}',secret_refs:'{}',volume_mounts:'[]',related_tables:'[]'})
function parse(name,type){try{const v=JSON.parse(json[name]);if(type==='array'&&!Array.isArray(v))throw new Error();if(type==='object'&&(Array.isArray(v)||v===null||typeof v!=='object'))throw new Error();return v}catch{throw new Error(`${name} 不是有效的 ${type==='array'?'JSON 数组':'JSON 对象'}`)}}
async function loadImages(){images.value=[];form.runtime.fixed_image_version_id=null;if(form.project_id)images.value=(await api.get(`/projects/${form.project_id}/images`)).data.filter(x=>x.build_status==='SUCCESS')}
async function load(){projects.value=(await api.get('/projects')).data;servers.value=(await api.get('/servers')).data;if(editing.value){const {data}=await api.get(`/tasks/${route.params.id}`);Object.assign(form,data);Object.assign(form.runtime,data.runtime);Object.assign(form.schedule,data.schedule);json.arguments=JSON.stringify(data.arguments||[],null,2);json.keyword_arguments=JSON.stringify(data.keyword_arguments||{},null,2);json.container_command=JSON.stringify(data.runtime?.container_command||[],null,2);json.environment_variables=JSON.stringify(data.runtime?.environment_variables||{},null,2);json.secret_refs=JSON.stringify(data.runtime?.secret_refs||{},null,2);json.volume_mounts=JSON.stringify(data.runtime?.volume_mounts||[],null,2);json.related_tables=JSON.stringify(data.related_tables||[],null,2);const fixed=data.runtime?.fixed_image_version_id;await loadImages();form.runtime.fixed_image_version_id=fixed}}
async function save(){saving.value=true;try{const payload=JSON.parse(JSON.stringify(form));payload.arguments=parse('arguments','array');payload.keyword_arguments=parse('keyword_arguments','object');payload.related_tables=parse('related_tables','array');payload.runtime.container_command=parse('container_command','array');payload.runtime.environment_variables=parse('environment_variables','object');payload.runtime.secret_refs=parse('secret_refs','object');payload.runtime.volume_mounts=parse('volume_mounts','array');if(editing.value)await api.put(`/tasks/${route.params.id}`,payload);else await api.post('/tasks',payload);ElMessage.success('保存成功');router.push('/tasks')}catch(e){ElMessage.error(e.response?.data?.detail||e.message||'保存失败')}finally{saving.value=false}}
onMounted(load)
</script>

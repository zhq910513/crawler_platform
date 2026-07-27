<template>
  <div class="page-card">
    <div class="toolbar">
      <el-select v-model="query.task_id" clearable filterable placeholder="选择任务" style="width:260px"><el-option v-for="t in tasks" :key="t.task_id" :label="t.task_name" :value="t.task_id"/></el-select>
      <el-select v-model="query.status" clearable placeholder="运行状态" style="width:160px"><el-option v-for="s in statuses" :key="s" :label="s" :value="s"/></el-select>
      <el-button type="primary" @click="load">查询</el-button>
    </div>
    <el-table :data="rows" v-loading="loading">
      <el-table-column prop="run_no" label="运行编号" min-width="230" />
      <el-table-column prop="task_name" label="任务名称" min-width="180" />
      <el-table-column prop="trigger_type" label="触发方式" width="100" />
      <el-table-column label="状态" width="110"><template #default="s"><el-tag :type="tagType(s.row.status)">{{ s.row.status }}</el-tag></template></el-table-column>
      <el-table-column prop="attempt" label="次数" width="70" />
      <el-table-column prop="server_id" label="服务器ID" width="95" />
      <el-table-column prop="image_tag" label="镜像版本" min-width="150" show-overflow-tooltip />
      <el-table-column prop="started_at" label="开始时间" width="190" />
      <el-table-column prop="duration_ms" label="耗时" width="110"><template #default="s">{{ duration(s.row.duration_ms) }}</template></el-table-column>
      <el-table-column prop="error_message" label="异常摘要" min-width="220" show-overflow-tooltip />
      <el-table-column label="操作" width="90"><template #default="s"><el-button link type="primary" @click="$router.push(`/runs/${s.row.run_id}`)">详情</el-button></template></el-table-column>
    </el-table>
    <div style="display:flex;justify-content:flex-end;margin-top:16px"><el-pagination v-model:current-page="query.page" v-model:page-size="query.page_size" :total="total" layout="total, sizes, prev, pager, next" @change="load" /></div>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'; import api from '../api'; import { useRoute } from 'vue-router'
const route=useRoute(),rows=ref([]),tasks=ref([]),total=ref(0),loading=ref(false),statuses=['QUEUED','CLAIMED','RUNNING','SUCCESS','FAILED','TIMEOUT','CANCELLED','LOST','SKIPPED']
const query=reactive({task_id:route.query.task_id?Number(route.query.task_id):null,status:'',page:1,page_size:30})
function tagType(v){return ({SUCCESS:'success',FAILED:'danger',TIMEOUT:'danger',LOST:'danger',RUNNING:'primary',CLAIMED:'warning',QUEUED:'info',CANCELLED:'info',SKIPPED:'info'})[v]||'info'}
function duration(ms){if(ms==null)return '-';if(ms<1000)return `${ms}ms`;return `${(ms/1000).toFixed(1)}s`}
async function load(){loading.value=true;try{const {data}=await api.get('/runs',{params:query});rows.value=data.items;total.value=data.total}finally{loading.value=false}}
onMounted(async()=>{tasks.value=(await api.get('/tasks',{params:{page_size:200}})).data.items;load()})
</script>

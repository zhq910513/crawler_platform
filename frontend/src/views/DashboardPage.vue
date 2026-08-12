<template>
  <div class="page-card">
    <div class="toolbar"><el-button type="primary" @click="load">刷新</el-button></div>
    <el-row :gutter="16">
      <el-col v-for="item in cards" :key="item.title" :span="4">
        <el-card><div class="muted">{{ item.title }}</div><h2>{{ item.value }}</h2></el-card>
      </el-col>
    </el-row>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { listDashboardSummaries } from '../api/platform'
import type { DashboardSummary } from '../types/api'
const summary = ref<DashboardSummary>({ projectCount: 0, serverCount: 0, taskCount: 0, runningCount: 0, waitingCount: 0 })
const cards = computed(() => [
  { title: '项目数量', value: summary.value.projectCount }, { title: '服务器', value: summary.value.serverCount }, { title: '任务数量', value: summary.value.taskCount }, { title: '运行中', value: summary.value.runningCount }, { title: '等待资源', value: summary.value.waitingCount },
])
async function load() { summary.value = await listDashboardSummaries() }
onMounted(load)
</script>

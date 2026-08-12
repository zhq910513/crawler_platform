<template>
  <div class="page-card platforms-page">
    <div class="toolbar platform-toolbar">
      <div>
        <h3>采集目标</h3>
        <p class="muted">采集目标是被采集的网站或系统，例如 Oilchem、JDL、CommerceHub。当前页面帮助确认项目任务中涉及的平台，具体账号请到“账号资源”维护。</p>
      </div>
      <div>
        <el-select v-if="sessionState.user?.isSuperAdmin" v-model="companyId" filterable placeholder="选择公司" style="width: 240px" @change="load">
          <el-option v-for="company in companies" :key="company.companyId" :label="company.companyName" :value="company.companyId" />
        </el-select>
        <el-button @click="load">刷新</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon title="平台信息主要由爬虫项目任务定义和账号资源状态自动汇总。本轮先用于定位与检查，后续可扩展为平台模板配置中心。" />

    <el-empty v-if="!status?.counts.platformCodeCount" description="暂未发现采集目标">
      <div class="empty-hint">请先部署爬虫项目，平台会从任务定义中识别采集目标。</div>
    </el-empty>
    <div v-else class="platform-summary">
      <div class="metric-card"><div class="metric-label">已识别平台</div><div class="metric-value">{{ status?.counts.platformCodeCount || 0 }}</div></div>
      <div class="metric-card"><div class="metric-label">可用账号</div><div class="metric-value">{{ status?.counts.accountTotal || 0 }}</div></div>
      <div class="metric-card"><div class="metric-label">账号异常</div><div class="metric-value">{{ status?.counts.accountNeedAttention || 0 }}</div></div>
    </div>
  </div>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getCompanySetupStatus, listCompanies } from '../api/platform'
import { sessionState } from '../stores/session'
import type { Company, CompanySetupStatus } from '../types/api'
const route = useRoute()
const companies = ref<Company[]>([])
const companyId = ref<number>(Number(route.query.companyId || 0))
const status = ref<CompanySetupStatus | null>(null)
async function load() { companies.value = await listCompanies(); if (!companyId.value) companyId.value = sessionState.user?.companyId || companies.value[0]?.companyId || 0; if (companyId.value) status.value = await getCompanySetupStatus(companyId.value) }
onMounted(load)
</script>
<style scoped>
.platform-toolbar { align-items: flex-start; justify-content: space-between; }
.platform-toolbar h3 { margin: 0 0 6px; }
.empty-hint { margin-bottom: 12px; color: #64748b; }
.platform-summary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-top: 16px; }
@media (max-width: 980px) { .platform-summary { grid-template-columns: 1fr; } }
</style>

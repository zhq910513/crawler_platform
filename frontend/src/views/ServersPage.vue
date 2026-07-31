<template>
  <div class="page-card">
    <div class="toolbar"><el-button v-if="sessionState.user?.isSuperAdmin" type="primary" @click="dialogVisible = true">新增服务器</el-button><el-button @click="load">刷新</el-button></div>
    <el-table :data="rows" border><el-table-column label="服务器名称" prop="serverName" /><el-table-column label="服务器编码" prop="serverCode" /><el-table-column label="服务器IP" prop="serverIp" /><el-table-column label="管理状态"><template #default="s">{{ zh(s.row.manageStatus) }}</template></el-table-column><el-table-column label="健康状态"><template #default="s">{{ zh(s.row.healthStatus) }}</template></el-table-column><el-table-column label="容量状态"><template #default="s">{{ zh(s.row.capacityStatus) }}</template></el-table-column><el-table-column label="最大容器数" prop="maxContainerSlots" /></el-table>
    <el-dialog v-model="dialogVisible" title="新增服务器" width="520px"><el-form label-position="top"><el-form-item label="公司"><el-select v-model="form.companyId"><el-option v-for="company in companies" :key="company.companyId" :label="company.companyName" :value="company.companyId" /></el-select></el-form-item><el-form-item label="服务器编码"><el-input v-model="form.serverCode" /></el-form-item><el-form-item label="服务器名称"><el-input v-model="form.serverName" /></el-form-item><el-form-item label="服务器IP"><el-input v-model="form.serverIp" /></el-form-item><el-form-item label="最大容器数"><el-input-number v-model="form.maxContainerSlots" :min="1" /></el-form-item></el-form><template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template></el-dialog>
  </div>
</template>
<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { createServer, listCompanies, listServers } from '../api/platform'
import { sessionState } from '../stores/session'
import type { Company, ServerNode } from '../types/api'
import { zh } from '../utils/dictionaries'
const rows = ref<ServerNode[]>([]); const companies = ref<Company[]>([]); const dialogVisible = ref(false); const form = reactive({ companyId: 0, serverCode: '', serverName: '', serverIp: '', maxContainerSlots: 4 })
async function load() { companies.value = await listCompanies(); if (!form.companyId) form.companyId = sessionState.user?.companyId || companies.value[0]?.companyId || 0; rows.value = await listServers(sessionState.user?.isSuperAdmin ? undefined : sessionState.user?.companyId || undefined) }
async function save() { await createServer(form); dialogVisible.value = false; await load() }
onMounted(load)
</script>

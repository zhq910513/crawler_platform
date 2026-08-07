<template>
  <div class="page-card">
    <div class="toolbar"><el-button type="primary" @click="dialogVisible = true">新增公司</el-button><el-button @click="load">刷新</el-button></div>
    <el-table :data="rows" stripe>
      <el-table-column label="公司名称" prop="companyName" min-width="180" />
      <el-table-column label="公司标识" prop="companyCode" min-width="140" />
      <el-table-column label="状态"><template #default="s">{{ zh(s.row.status) }}</template></el-table-column>
      <el-table-column label="时区" prop="timezone" />
      <el-table-column label="创建时间"><template #default="s">{{ formatTime(s.row.createdAt) }}</template></el-table-column>
      <el-table-column label="操作" width="190"><template #default="s"><el-button size="small" @click="createToken(s.row.companyId)">生成项目发布凭证</el-button></template></el-table-column>
    </el-table>
    <el-dialog v-model="dialogVisible" title="新增公司" width="420px">
      <el-form label-position="top">
        <el-form-item label="公司标识"><el-input v-model="form.companyCode" /></el-form-item>
        <el-form-item label="公司名称"><el-input v-model="form.companyName" /></el-form-item>
        <el-form-item label="时区"><el-input v-model="form.timezone" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createCompany, createDiscoveryToken, listCompanies } from '../api/platform'
import type { Company } from '../types/api'
import { formatTime, zh } from '../utils/dictionaries'
const rows = ref<Company[]>([]); const dialogVisible = ref(false); const form = reactive({ companyCode: '', companyName: '', timezone: 'Asia/Shanghai' })
async function load() { rows.value = await listCompanies() }
async function save() { await createCompany(form); dialogVisible.value = false; ElMessage.success('公司已创建，请继续配置数据库、采集平台、平台账号和执行节点。'); await load() }
async function createToken(companyId: number) {
  const data = await createDiscoveryToken(companyId)
  await ElMessageBox.alert(`该凭证用于爬虫项目流水线向平台发布版本，不用于接入执行节点。请将下面内容保存到代码仓库的安全变量中，只显示一次：\n\n${data.discoveryToken}`, '项目发布凭证')
}
onMounted(load)
</script>

<template>
  <div class="page-card companies-page">
    <div class="toolbar company-toolbar">
      <div>
        <h3>公司管理</h3>
        <p class="muted">创建公司后，通过配置助手引导完成数据库、执行节点、项目、账号和任务调度准备。</p>
      </div>
      <div><el-button type="primary" @click="dialogVisible = true">新增公司</el-button><el-button @click="load">刷新</el-button></div>
    </div>

    <el-empty v-if="!rows.length" description="还没有公司">
      <div class="empty-hint">新增公司后，系统会打开配置助手，帮助你定位后续配置界面。</div>
      <el-button type="primary" @click="dialogVisible = true">新增公司</el-button>
    </el-empty>

    <el-table v-else :data="rows" stripe>
      <el-table-column label="公司名称" prop="companyName" min-width="180" />
      <el-table-column label="公司标识" prop="companyCode" min-width="140" />
      <el-table-column label="状态"><template #default="s">{{ zh(s.row.status) }}</template></el-table-column>
      <el-table-column label="时区" prop="timezone" />
      <el-table-column label="创建时间"><template #default="s">{{ formatTime(s.row.createdAt) }}</template></el-table-column>
      <el-table-column label="操作" width="150"><template #default="s"><el-button size="small" type="primary" plain @click="openConfigAssistant(s.row.companyId, s.row.companyName)">继续配置</el-button></template></el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新增公司" width="460px">
      <el-form label-position="top">
        <el-form-item label="公司标识"><el-input v-model="form.companyCode" placeholder="例如：ulike" /></el-form-item>
        <el-form-item label="公司名称"><el-input v-model="form.companyName" placeholder="请输入公司名称" /></el-form-item>
        <el-form-item label="时区"><el-input v-model="form.timezone" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" @click="save">保存并打开配置助手</el-button></template>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createCompany, listCompanies } from '../api/platform'
import type { Company } from '../types/api'
import { formatTime, zh } from '../utils/dictionaries'
import { openConfigAssistant } from '../stores/configAssistant'
const rows = ref<Company[]>([])
const dialogVisible = ref(false)
const form = reactive({ companyCode: '', companyName: '', timezone: 'Asia/Shanghai' })
async function load() { rows.value = await listCompanies() }
async function save() {
  const company = await createCompany(form)
  dialogVisible.value = false
  ElMessage.success('公司已创建，已打开配置助手')
  form.companyCode = ''; form.companyName = ''; form.timezone = 'Asia/Shanghai'
  await load()
  await openConfigAssistant(company.companyId, company.companyName)
}
onMounted(load)
</script>
<style scoped>
.company-toolbar { justify-content: space-between; align-items: flex-start; }
.company-toolbar h3 { margin: 0 0 6px; }
.empty-hint { margin-bottom: 12px; color: #64748b; }
</style>

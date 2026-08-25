<template>
  <div class="page-card companies-page">
    <div class="toolbar company-toolbar">
      <div>
        <h3>公司管理</h3>
        <p class="muted">创建公司后，通过配置助手引导完成数据库、执行节点、项目、账号和任务编排准备。</p>
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
      <el-table-column label="操作" width="250"><template #default="s">
        <el-button size="small" type="primary" plain @click="openConfigAssistant(s.row.companyId, s.row.companyName)">继续配置</el-button>
        <el-button size="small" @click="generateSecret(s.row)">生成接入密钥</el-button>
      </template></el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新增公司" width="460px">
      <el-form label-position="top">
        <el-form-item label="公司标识"><el-input v-model="form.companyCode" placeholder="例如：ulike" /></el-form-item>
        <el-form-item label="公司名称"><el-input v-model="form.companyName" placeholder="请输入公司名称" /></el-form-item>
        <el-form-item label="时区"><el-input v-model="form.timezone" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" @click="save">保存并打开配置助手</el-button></template>
    </el-dialog>

    <el-dialog v-model="secretDialogVisible" title="公司接入密钥" width="620px" :close-on-click-modal="false">
      <el-alert type="warning" show-icon :closable="false" title="密钥只显示这一次，关闭后无法查看原文；当前仅作为平台内部构建中心或受控导入流程使用，不建议写入爬虫项目仓库。" />
      <div class="secret-meta">
        <div><span class="muted">公司：</span>{{ secretCompanyName }}</div>
        <div><span class="muted">编号：</span>{{ secretId || '-' }}</div>
      </div>
      <el-input v-model="secretValue" type="textarea" :rows="4" readonly />
      <template #footer>
        <el-button @click="secretDialogVisible = false">关闭</el-button>
        <el-button type="primary" @click="copySecret">复制密钥</el-button>
      </template>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createCompany, createDiscoveryToken, listCompanies } from '../api/platform'
import { apiErrorData } from '../api/client'
import type { Company } from '../types/api'
import { formatTime, zh } from '../utils/dictionaries'
import { openConfigAssistant } from '../stores/configAssistant'
const rows = ref<Company[]>([])
const dialogVisible = ref(false)
const secretDialogVisible = ref(false)
const secretValue = ref('')
const secretId = ref<number | null>(null)
const secretCompanyName = ref('')
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
async function generateSecret(row: Company) {
  try {
    await ElMessageBox.confirm(`确认为“${row.companyName}”生成新的项目接入密钥？旧密钥不会自动失效，生成后原文只显示一次。`, '生成接入密钥确认', { type: 'warning' })
    const result = await createDiscoveryToken(row.companyId)
    secretValue.value = result.discoveryToken
    secretId.value = result.tokenId
    secretCompanyName.value = row.companyName
    secretDialogVisible.value = true
    ElMessage.success('接入密钥已生成，请立即复制保存')
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    const payload = apiErrorData<unknown>(error)
    ElMessage.error(payload?.message || '生成接入密钥失败')
  }
}
async function copySecret() {
  try {
    await navigator.clipboard.writeText(secretValue.value)
  } catch {
    const input = document.createElement('textarea')
    input.value = secretValue.value
    input.style.position = 'fixed'
    input.style.opacity = '0'
    document.body.appendChild(input)
    input.select()
    document.execCommand('copy')
    document.body.removeChild(input)
  }
  ElMessage.success('已复制')
}
onMounted(load)
</script>
<style scoped>
.company-toolbar { justify-content: space-between; align-items: flex-start; }
.company-toolbar h3 { margin: 0 0 6px; }
.empty-hint { margin-bottom: 12px; color: #64748b; }
.secret-meta { display: grid; gap: 6px; margin: 12px 0; }
</style>

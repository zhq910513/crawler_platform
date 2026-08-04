<template>
  <div class="page-card">
    <div class="toolbar">
      <el-button type="primary" @click="dialogVisible = true">新增用户</el-button>
      <el-button @click="load">刷新</el-button>
    </div>
    <el-table :data="rows" border>
      <el-table-column label="用户名称" prop="userName" min-width="140" />
      <el-table-column label="昵称" prop="nickName" min-width="140" />
      <el-table-column label="角色"><template #default="s">{{ zh(s.row.roleType) }}</template></el-table-column>
      <el-table-column label="归属公司"><template #default="s">{{ companyName(s.row.companyId) }}</template></el-table-column>
      <el-table-column label="状态"><template #default="s">{{ zh(s.row.status) }}</template></el-table-column>
      <el-table-column label="密码状态"><template #default="s"><el-tag :type="s.row.mustChangePassword ? 'warning' : 'success'">{{ s.row.mustChangePassword ? '需修改' : '正常' }}</el-tag></template></el-table-column>
      <el-table-column label="密码更新时间"><template #default="s">{{ formatTime(s.row.passwordUpdatedAt) }}</template></el-table-column>
      <el-table-column label="最近登录"><template #default="s">{{ formatTime(s.row.lastLoginAt) }}</template></el-table-column>
      <el-table-column label="操作" width="240">
        <template #default="s">
          <el-button size="small" @click="openReset(s.row)">重置密码</el-button>
          <el-button size="small" type="danger" @click="revoke(s.row.userId)">强制下线</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新增用户" width="520px">
      <el-form label-position="top">
        <el-form-item label="用户名称"><el-input v-model="form.userName" /></el-form-item>
        <el-form-item label="昵称"><el-input v-model="form.nickName" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="form.password" type="password" show-password /></el-form-item>
        <el-form-item label="角色"><el-select v-model="form.roleType"><el-option label="超级管理员" value="SUPER_ADMIN" /><el-option label="普通用户" value="NORMAL_USER" /></el-select></el-form-item>
        <el-form-item label="归属公司"><el-select v-model="form.companyId" clearable><el-option v-for="company in companies" :key="company.companyId" :label="company.companyName" :value="company.companyId" /></el-select></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="resetVisible" title="重置密码" width="460px">
      <el-alert title="重置后目标账号现有会话会立即失效。重置当前登录账号时，不会再次要求当前账号下次登录修改密码。" type="warning" show-icon :closable="false" class="reset-alert" />
      <el-form label-position="top">
        <el-form-item label="目标账号"><el-input :model-value="selectedUser?.userName || ''" disabled /></el-form-item>
        <el-form-item label="新密码"><el-input v-model="resetForm.newPassword" type="password" show-password autocomplete="new-password" /></el-form-item>
        <el-form-item label="下次登录强制修改"><el-switch v-model="resetForm.mustChangePassword" :disabled="selectedUser?.userId === sessionState.user?.userId" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="resetVisible = false">取消</el-button><el-button type="primary" @click="submitReset">确认重置</el-button></template>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createUser, listCompanies, listUsers, resetUserPassword, revokeUserSession } from '../api/platform'
import { sessionState } from '../stores/session'
import type { Company, UserAccount, UserCreateRequest } from '../types/api'
import { formatTime, zh } from '../utils/dictionaries'

const rows = ref<UserAccount[]>([])
const companies = ref<Company[]>([])
const dialogVisible = ref(false)
const resetVisible = ref(false)
const selectedUser = ref<UserAccount | null>(null)
const form = reactive<UserCreateRequest>({ userName: '', nickName: '', password: '', roleType: 'NORMAL_USER', companyId: null, status: 'ENABLED' })
const resetForm = reactive({ newPassword: '', mustChangePassword: true })

function companyName(companyId: number | null) {
  return companies.value.find((item) => item.companyId === companyId)?.companyName || '-'
}
async function load() {
  companies.value = await listCompanies()
  rows.value = await listUsers()
}
async function save() {
  await createUser(form)
  dialogVisible.value = false
  ElMessage.success('用户已创建')
  await load()
}
function openReset(user: UserAccount) {
  selectedUser.value = user
  resetForm.newPassword = ''
  resetForm.mustChangePassword = user.userId === sessionState.user?.userId ? false : true
  resetVisible.value = true
}
async function submitReset() {
  if (!selectedUser.value) return
  await ElMessageBox.confirm(`确认重置账号“${selectedUser.value.userName}”的密码并下线其现有会话？`, '重置密码确认', { type: 'warning' })
  const result = await resetUserPassword(selectedUser.value.userId, resetForm)
  resetVisible.value = false
  ElMessage.success(`密码已重置，已下线 ${result.revokedCount} 个会话`)
  await load()
}
async function revoke(userId: number) {
  await ElMessageBox.confirm('确定要强制下线该账号吗？', '强制下线确认', { type: 'warning' })
  const result = await revokeUserSession(userId, '您的账号已被管理员强制下线。')
  ElMessage.success(`已强制下线 ${result.revokedCount} 个会话`)
}
onMounted(load)
</script>
<style scoped>
.reset-alert { margin-bottom: 12px; }
</style>

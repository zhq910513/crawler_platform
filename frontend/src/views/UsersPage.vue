<template>
  <div class="page-card">
    <div class="toolbar"><el-button type="primary" @click="dialogVisible = true">新增用户</el-button><el-button @click="load">刷新</el-button></div>
    <el-table :data="rows" border>
      <el-table-column label="用户名称" prop="userName" /><el-table-column label="昵称" prop="nickName" />
      <el-table-column label="角色"><template #default="s">{{ zh(s.row.roleType) }}</template></el-table-column>
      <el-table-column label="归属公司"><template #default="s">{{ companyName(s.row.companyId) }}</template></el-table-column>
      <el-table-column label="状态"><template #default="s">{{ zh(s.row.status) }}</template></el-table-column>
      <el-table-column label="最近登录"><template #default="s">{{ formatTime(s.row.lastLoginAt) }}</template></el-table-column>
      <el-table-column label="操作"><template #default="s"><el-button size="small" type="danger" @click="revoke(s.row.userId)">强制下线</el-button></template></el-table-column>
    </el-table>
    <el-dialog v-model="dialogVisible" title="新增用户" width="520px"><el-form label-position="top"><el-form-item label="用户名称"><el-input v-model="form.userName" /></el-form-item><el-form-item label="昵称"><el-input v-model="form.nickName" /></el-form-item><el-form-item label="密码"><el-input v-model="form.password" type="password" /></el-form-item><el-form-item label="角色"><el-select v-model="form.roleType"><el-option label="超级管理员" value="SUPER_ADMIN" /><el-option label="普通用户" value="NORMAL_USER" /></el-select></el-form-item><el-form-item label="归属公司"><el-select v-model="form.companyId" clearable><el-option v-for="company in companies" :key="company.companyId" :label="company.companyName" :value="company.companyId" /></el-select></el-form-item></el-form><template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template></el-dialog>
  </div>
</template>
<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createUser, listCompanies, listUsers, revokeUserSession } from '../api/platform'
import type { Company, UserAccount, UserCreateRequest } from '../types/api'
import { formatTime, zh } from '../utils/dictionaries'
const rows = ref<UserAccount[]>([]); const companies = ref<Company[]>([]); const dialogVisible = ref(false); const form = reactive<UserCreateRequest>({ userName: '', nickName: '', password: '', roleType: 'NORMAL_USER', companyId: null, status: 'ENABLED' })
function companyName(companyId: number | null) { return companies.value.find((item) => item.companyId === companyId)?.companyName || '-' }
async function load() { companies.value = await listCompanies(); rows.value = await listUsers() }
async function save() { await createUser(form); dialogVisible.value = false; await load() }
async function revoke(userId: number) { await ElMessageBox.confirm('确定要强制下线该账号吗？', '强制下线确认', { type: 'warning' }); const result = await revokeUserSession(userId, '您的账号已被管理员强制下线。'); ElMessage.success(`已强制下线 ${result.revokedCount} 个会话`) }
onMounted(load)
</script>

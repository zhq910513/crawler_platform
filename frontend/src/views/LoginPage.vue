<template>
  <div class="login-page">
    <el-card class="login-card">
      <h2>爬虫管理平台</h2>
      <el-form label-position="top" @keyup.enter="submit">
        <el-form-item label="账号"><el-input v-model="form.userName" autocomplete="username" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="form.password" type="password" autocomplete="current-password" show-password /></el-form-item>
        <el-button type="primary" class="full-width" :loading="loading" @click="submit">登录</el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { createSession } from '../api/sessions'
import { setSession } from '../stores/session'
import type { LoginConflictData } from '../types/api'
import { apiErrorData } from '../api/client'

const router = useRouter()
const form = reactive({ userName: '', password: '', forceLoginToken: null as string | null })
const loading = ref(false)
async function submit() {
  loading.value = true
  try {
    const data = await createSession(form)
    setSession(data.accessToken, data.sessionId, data.user)
    await router.push(data.user.isSuperAdmin ? '/dashboard' : '/projects')
  } catch (error) {
    const payload = apiErrorData<LoginConflictData>(error)
    if (payload?.code === 40901 && payload.data?.forceLoginToken) {
      await ElMessageBox.confirm(`该账号当前正在使用中。最近操作：${payload.data.lastActiveAt}，终端：${payload.data.deviceName}。是否强制登录？`, '账号在线提示', { confirmButtonText: '强制登录', cancelButtonText: '取消登录', type: 'warning' })
      form.forceLoginToken = payload.data.forceLoginToken
      await submit()
      return
    }
    ElMessage.error(payload?.message || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page { height: 100vh; display: flex; align-items: center; justify-content: center; background: linear-gradient(135deg, #0f172a, #1d4ed8); }
.login-card { width: 380px; }
h2 { margin: 0 0 24px; text-align: center; }
</style>

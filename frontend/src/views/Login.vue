<template>
  <div class="login-page">
    <el-card class="login-card">
      <h2>crawler_platform</h2>
      <p class="muted">容器化任务调度、日志与服务器监控</p>
      <el-form :model="form" @keyup.enter="submit">
        <el-form-item><el-input v-model="form.user_name" size="large" placeholder="用户名" prefix-icon="User" /></el-form-item>
        <el-form-item><el-input v-model="form.password" size="large" type="password" show-password placeholder="密码" prefix-icon="Lock" /></el-form-item>
        <el-button type="primary" size="large" :loading="loading" style="width:100%" @click="submit">登录</el-button>
      </el-form>
    </el-card>
  </div>
</template>
<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import api from '../api'
import { setAuth } from '../auth'
const router = useRouter(); const loading = ref(false)
const form = reactive({ user_name: 'admin', password: '' })
async function submit() {
  loading.value = true
  try { const { data } = await api.post('/auth/login', form); setAuth(data.access_token, data.user); router.push('/dashboard') }
  catch (e) { ElMessage.error(e.response?.data?.detail || '登录失败') }
  finally { loading.value = false }
}
</script>
<style scoped>
.login-page { min-height: 100vh; display:flex; align-items:center; justify-content:center; background:linear-gradient(135deg,#17233d,#2b4b80); }
.login-card { width:420px; padding:20px; } h2 { margin:0 0 8px; } p { margin:0 0 24px; }
</style>

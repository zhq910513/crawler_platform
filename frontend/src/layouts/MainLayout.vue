<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="brand"><el-icon><Monitor /></el-icon><span>crawler_platform</span></div>
      <el-menu :default-active="$route.path" router background-color="#17233d" text-color="#bfcbd9" active-text-color="#409eff">
        <el-menu-item index="/tasks"><el-icon><List /></el-icon><span>任务管理</span></el-menu-item>
        <template v-if="isAdmin">
          <el-menu-item index="/dashboard"><el-icon><DataBoard /></el-icon><span>首页</span></el-menu-item>
          <el-menu-item index="/runs"><el-icon><Clock /></el-icon><span>执行记录</span></el-menu-item>
          <el-menu-item index="/servers"><el-icon><Cpu /></el-icon><span>服务器监控</span></el-menu-item>
          <el-menu-item index="/projects"><el-icon><Box /></el-icon><span>项目与镜像</span></el-menu-item>
          <el-menu-item index="/operations"><el-icon><Document /></el-icon><span>操作日志</span></el-menu-item>
          <el-menu-item index="/users"><el-icon><User /></el-icon><span>用户管理</span></el-menu-item>
          <el-menu-item index="/settings"><el-icon><Setting /></el-icon><span>系统设置</span></el-menu-item>
        </template>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div>{{ $route.meta.title || 'crawler_platform' }}</div>
        <el-dropdown @command="handleCommand">
          <span class="user"><el-icon><UserFilled /></el-icon>{{ authState.user?.nick_name }}<el-icon><ArrowDown /></el-icon></span>
          <template #dropdown><el-dropdown-menu><el-dropdown-item command="logout">退出登录</el-dropdown-item></el-dropdown-menu></template>
        </el-dropdown>
      </el-header>
      <el-main class="main"><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { authState, clearAuth, isAdmin } from '../auth'
import { useRouter } from 'vue-router'
const router = useRouter()
function handleCommand(command) { if (command === 'logout') { clearAuth(); router.push('/login') } }
</script>

<style scoped>
.layout { min-height: 100vh; }
.aside { background: #17233d; color: white; }
.brand { height: 60px; display: flex; align-items: center; gap: 10px; padding: 0 20px; font-weight: 700; font-size: 17px; border-bottom: 1px solid rgba(255,255,255,.08); }
.el-menu { border-right: 0; }
.header { height: 60px; background: #fff; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
.user { display: flex; align-items: center; gap: 6px; cursor: pointer; }
.main { padding: 18px; }
</style>

<template>
  <div class="settings-page">
    <div class="page-card">
      <div class="section-title first-section"><h3>基础配置</h3><el-button type="primary" :loading="savingBase" @click="saveBaseSettings">保存</el-button></div>
      <el-form label-position="top" class="base-form">
        <el-form-item label="控制端公网回调地址">
          <el-input v-model="baseForm.controlPlanePublicBaseUrl" placeholder="例如：http://公网IP 或 https://crawler.example.com" />
          <div class="field-hint">代码构建流程和外部执行节点访问控制端服务时使用。通常就是你当前打开平台的公网 IP 或域名；只有实际使用非 80/443 端口时才需要带端口。</div>
        </el-form-item>
        <div class="base-status"><el-tag :type="settings?.controlPlanePublicBaseUrlConfigured ? 'success' : 'warning'" effect="light">{{ settings?.controlPlanePublicBaseUrlConfigured ? '已配置' : '未配置' }}</el-tag><span class="muted">来源：{{ settings?.controlPlanePublicBaseUrlSource || '-' }}</span></div>
        <el-alert v-if="settings?.controlPlanePublicBaseUrlWarnings?.length" type="warning" show-icon :closable="false" :title="settings.controlPlanePublicBaseUrlWarnings.join('；')" />
        <div v-if="baseForm.controlPlanePublicBaseUrl" class="command-preview">连通性验证：curl -fsSL {{ baseForm.controlPlanePublicBaseUrl }}/health && echo</div>
      </el-form>
    </div>

    <div class="page-card">
      <div class="section-title"><h3>告警通知</h3><div><el-button type="primary" @click="dialogVisible = true">新增渠道</el-button><el-button @click="load">刷新</el-button></div></div>
      <el-empty v-if="!rows.length" description="暂无告警渠道">
        <div class="empty-hint">添加邮箱、飞书或企业微信后，系统可以在任务失败时通知你。</div>
        <el-button type="primary" @click="dialogVisible = true">新增渠道</el-button>
      </el-empty>
      <el-table v-else :data="rows" stripe>
        <el-table-column label="配置名称" prop="channelName" />
        <el-table-column label="类型"><template #default="s">{{ zh(s.row.channelType) }}</template></el-table-column>
        <el-table-column label="状态"><template #default="s">{{ zh(s.row.channelStatus) }}</template></el-table-column>
        <el-table-column label="严重告警"><template #default="s">{{ s.row.p0Only ? '仅严重告警' : '全部告警' }}</template></el-table-column>
        <el-table-column label="冷却时间" prop="cooldownSeconds" />
        <el-table-column label="最近测试" prop="lastTestResult" />
        <el-table-column label="操作" width="110"><template #default="s"><el-button size="small" @click="testChannel(s.row.channelId)">发送测试</el-button></template></el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dialogVisible" title="新增通知渠道" width="520px">
      <el-form label-position="top">
        <el-form-item label="配置名称"><el-input v-model="form.channelName" /></el-form-item>
        <el-form-item label="通知类型"><el-select v-model="form.channelType"><el-option label="飞书" value="FEISHU" /><el-option label="企业微信" value="WEWORK" /><el-option label="钉钉" value="DINGTALK" /><el-option label="邮箱" value="EMAIL" /></el-select></el-form-item>
        <el-form-item label="启用状态"><el-select v-model="form.channelStatus"><el-option label="停用" value="DISABLED" /><el-option label="启用" value="ENABLED" /></el-select></el-form-item>
        <el-form-item label="冷却时间（秒）"><el-input-number v-model="form.cooldownSeconds" :min="60" /></el-form-item>
        <el-form-item label="回调地址"><el-input v-model="webhookUrl" type="textarea" :rows="3" placeholder="请输入通知地址" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template>
    </el-dialog>

    <div class="page-card">
      <div class="section-title"><h3>告警事件</h3></div>
      <el-empty v-if="!alerts.length" description="暂无告警事件" />
      <el-table v-else :data="alerts" stripe>
        <el-table-column label="等级" width="90"><template #default="s">{{ zh(s.row.severity) }}</template></el-table-column>
        <el-table-column label="状态"><template #default="s">{{ zh(s.row.alertStatus) }}</template></el-table-column>
        <el-table-column label="标题" prop="title" />
        <el-table-column label="次数" prop="occurrenceCount" width="80" />
        <el-table-column label="最近发生" prop="lastSeenAt" />
        <el-table-column label="操作" width="150"><template #default="s"><el-button size="small" @click="ack(s.row.alertId)">确认</el-button><el-button size="small" @click="resolveItem(s.row.alertId)">恢复</el-button></template></el-table-column>
      </el-table>
    </div>
  </div>
</template>
<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { acknowledgeAlert, createNotificationChannel, getSystemSettings, listAlertEvents, listNotificationChannels, resolveAlert, testNotificationChannel, updateSystemSettings } from '../api/platform'
import type { AlertEvent, NotificationChannel, NotificationChannelCreateRequest, SystemSettings } from '../types/api'
import { zh } from '../utils/dictionaries'
const route = useRoute()
const rows = ref<NotificationChannel[]>([]); const alerts = ref<AlertEvent[]>([]); const dialogVisible = ref(false); const webhookUrl = ref(''); const savingBase = ref(false)
const settings = ref<SystemSettings | null>(null)
const baseForm = reactive({ controlPlanePublicBaseUrl: '' })
const form = reactive<NotificationChannelCreateRequest>({ scopeType: 'SYSTEM', channelName: '', channelType: 'FEISHU', channelStatus: 'DISABLED', p0Only: true, cooldownSeconds: 1800, config: {} })
async function load() { settings.value = await getSystemSettings(); baseForm.controlPlanePublicBaseUrl = settings.value.controlPlanePublicBaseUrl || ''; rows.value = await listNotificationChannels(); alerts.value = await listAlertEvents() }
async function saveBaseSettings() { savingBase.value = true; try { settings.value = await updateSystemSettings({ controlPlanePublicBaseUrl: baseForm.controlPlanePublicBaseUrl }); ElMessage.success('基础配置已保存') } finally { savingBase.value = false } }
async function save() { await createNotificationChannel({ ...form, config: webhookUrl.value ? { webhook: webhookUrl.value } : {} }); dialogVisible.value = false; webhookUrl.value = ''; await load() }
async function testChannel(channelId: number) { const result = await testNotificationChannel(channelId, '爬虫管理平台测试通知', '这是一条告警渠道测试消息。'); if (result.success) { ElMessage.success(result.message) } else { ElMessage.warning(result.message) } await load() }
async function ack(alertId: number) { await acknowledgeAlert(alertId); await load() }
async function resolveItem(alertId: number) { await resolveAlert(alertId); await load() }
onMounted(async () => { await load(); if (route.query.focus === 'controlPlaneUrl') setTimeout(() => document.querySelector('.base-form input')?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 100) })
</script>
<style scoped>
.first-section { margin-top: 0; }
.base-form { max-width: 760px; }
.field-hint { color: #64748b; font-size: 12px; margin-top: 6px; }
.base-status { display: flex; gap: 10px; align-items: center; margin-top: 8px; }
.command-preview { margin-top: 12px; padding: 10px 12px; border-radius: 10px; background: #111827; color: #e5e7eb; font-size: 12px; word-break: break-all; }
.empty-hint { margin-bottom: 12px; color: #64748b; }
</style>

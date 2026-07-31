<template>
  <div class="page-card">
    <h3>P0 告警通知配置</h3>
    <p class="muted">当前仅严重 P0 事件会外部通知，支持飞书、企业微信、钉钉和邮箱；P1/P2/P3 只记录事件。</p>
    <div class="toolbar"><el-button type="primary" @click="dialogVisible = true">新增通知渠道</el-button><el-button @click="load">刷新</el-button></div>
    <el-table :data="rows" border><el-table-column label="配置名称" prop="channelName" /><el-table-column label="类型"><template #default="s">{{ zh(s.row.channelType) }}</template></el-table-column><el-table-column label="状态"><template #default="s">{{ zh(s.row.channelStatus) }}</template></el-table-column><el-table-column label="仅P0告警"><template #default="s">{{ s.row.p0Only ? '是' : '否' }}</template></el-table-column><el-table-column label="冷却秒数" prop="cooldownSeconds" /><el-table-column label="最近测试" prop="lastTestResult" /><el-table-column label="操作"><template #default="s"><el-button size="small" @click="testChannel(s.row.channelId)">发送测试</el-button></template></el-table-column></el-table>
    <el-dialog v-model="dialogVisible" title="新增通知渠道" width="520px"><el-form label-position="top"><el-form-item label="配置名称"><el-input v-model="form.channelName" /></el-form-item><el-form-item label="通知类型"><el-select v-model="form.channelType"><el-option label="飞书" value="FEISHU" /><el-option label="企业微信" value="WEWORK" /><el-option label="钉钉" value="DINGTALK" /><el-option label="邮箱" value="EMAIL" /></el-select></el-form-item><el-form-item label="启用状态"><el-select v-model="form.channelStatus"><el-option label="停用" value="DISABLED" /><el-option label="启用" value="ENABLED" /></el-select></el-form-item><el-form-item label="告警冷却秒数"><el-input-number v-model="form.cooldownSeconds" :min="60" /></el-form-item><el-form-item label="基础配置JSON"><el-input v-model="configText" type="textarea" :rows="6" /></el-form-item></el-form><template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template></el-dialog>
  <h3 style="margin-top:24px">P0 告警事件</h3><el-table :data="alerts" border><el-table-column label="等级" prop="severity" width="80"/><el-table-column label="状态"><template #default="s">{{ zh(s.row.alertStatus) }}</template></el-table-column><el-table-column label="标题" prop="title"/><el-table-column label="事件指纹" prop="fingerprint"/><el-table-column label="次数" prop="occurrenceCount" width="80"/><el-table-column label="最近发生" prop="lastSeenAt"/><el-table-column label="操作"><template #default="s"><el-button size="small" @click="ack(s.row.alertId)">确认</el-button><el-button size="small" @click="resolveItem(s.row.alertId)">恢复</el-button></template></el-table-column></el-table></div>
</template>
<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { acknowledgeAlert, createNotificationChannel, listAlertEvents, listNotificationChannels, resolveAlert, testNotificationChannel } from '../api/platform'
import type { AlertEvent, NotificationChannel, NotificationChannelCreateRequest } from '../types/api'
import { zh } from '../utils/dictionaries'
const rows = ref<NotificationChannel[]>([]); const alerts = ref<AlertEvent[]>([]); const dialogVisible = ref(false); const configText = ref('{"webhook":""}')
const form = reactive<NotificationChannelCreateRequest>({ scopeType: 'SYSTEM', channelName: '', channelType: 'FEISHU', channelStatus: 'DISABLED', p0Only: true, cooldownSeconds: 1800, config: {} })
async function load() { rows.value = await listNotificationChannels(); alerts.value = await listAlertEvents() }
async function save() { await createNotificationChannel({ ...form, config: JSON.parse(configText.value) }); dialogVisible.value = false; await load() }
async function testChannel(channelId: number) { const result = await testNotificationChannel(channelId, '爬虫管理平台测试通知', '这是一条 P0 告警渠道测试消息。'); if (result.success) { ElMessage.success(result.message) } else { ElMessage.warning(result.message) } await load() }
async function ack(alertId: number) { await acknowledgeAlert(alertId); await load() }
async function resolveItem(alertId: number) { await resolveAlert(alertId); await load() }
onMounted(load)
</script>

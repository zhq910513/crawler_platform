<template>
  <div class="dashboard-page">
    <div class="page-card overview-card">
      <div class="metric-grid">
        <div v-for="item in cards" :key="item.title" class="metric-card">
          <span>{{ item.title }}</span>
          <strong>{{ item.value }}</strong>
        </div>
      </div>
    </div>

    <div v-if="preflight" class="page-card health-card" :class="`health-${overallStatus.toLowerCase()}`">
      <div class="health-main">
        <span class="status-dot" :class="`dot-${overallStatus.toLowerCase()}`"></span>
        <div>
          <div class="health-title">{{ platformStatusTitle }}</div>
          <div class="health-summary">{{ platformStatusSummary }}</div>
          <div class="health-meta">已验证 {{ preflight.verifiedCount }} · 待自动验证 {{ preflight.pendingCount }} · 异常 {{ currentProblemCount }}</div>
        </div>
      </div>
      <div class="health-actions">
        <el-button v-if="autoFixCandidate" type="success" :loading="actionRunning" @click="runAutoFix()">{{ autoFixCandidate.actionButtonLabel || '自动处理' }}</el-button>
        <el-button :loading="loading" @click="load('AUTO')">刷新</el-button>
        <el-button @click="detailVisible = true">查看详情</el-button>
      </div>
    </div>

    <div v-if="currentProblems.length" class="page-card issues-card">
      <div class="issues-header">
        <div>
          <div class="section-title-small">当前异常</div>
          <div class="muted">{{ currentProblemCount }} 项需要关注</div>
        </div>
        <el-button text @click="detailVisible = true">查看全部</el-button>
      </div>
      <div class="issue-list">
        <div v-for="item in topProblems" :key="item.key" class="issue-row">
          <span class="issue-indicator" :class="`issue-${item.status.toLowerCase()}`"></span>
          <div class="issue-copy">
            <div class="issue-title">{{ item.label }}</div>
            <div class="muted issue-message">{{ item.impact || item.message }}</div>
          </div>
          <el-button v-if="item.route" text @click="goRoute(item.route)">查看</el-button>
        </div>
      </div>
    </div>

    <div v-else-if="preflight" class="quiet-state">
      <span class="quiet-check">✓</span>
      <span>暂无需要处理的问题</span>
    </div>

    <el-drawer v-model="detailVisible" title="平台状态详情" size="640px" class="preflight-drawer">
      <template v-if="preflight">
        <div class="drawer-overview" :class="`drawer-${overallStatus.toLowerCase()}`">
          <div>
            <div class="drawer-title-row">
              <span class="status-dot" :class="`dot-${overallStatus.toLowerCase()}`"></span>
              <h3>{{ platformStatusTitle }}</h3>
            </div>
            <div class="muted">{{ preflight.checkSourceLabel || '页面自动检测' }} · {{ formatTime(preflight.checkedAt) }}</div>
          </div>
          <el-button type="primary" plain :loading="loading" @click="load('MANUAL')">重新检测</el-button>
        </div>

        <div v-if="actionResult" class="action-result" :class="`result-${String(actionResult.status || '').toLowerCase()}`">
          <div><strong>{{ actionResult.status === 'SUCCESS' ? '自动处理完成' : (actionResult.status === 'UNAVAILABLE' ? '当前不能一键处理' : '自动处理结果') }}</strong>：{{ actionResult.message || actionResult.stage }}</div>
          <div v-if="actionResult.stage" class="muted">阶段：{{ actionResult.stage }}</div>
          <pre v-if="actionResult.logs?.length" class="mini-log">{{ actionResult.logs.slice(-12).join('\n') }}</pre>
          <div v-if="actionResult.manualCommand" class="command-row"><span>手动兜底命令</span><el-button size="small" @click="copyText(actionResult.manualCommand || '')">复制</el-button></div>
          <pre v-if="actionResult.manualCommand" class="verify-command">{{ actionResult.manualCommand }}</pre>
        </div>

        <el-tabs class="detail-tabs">
          <el-tab-pane label="检测项">
            <div v-if="lastChanges.length" class="compact-change-box">
              <div class="section-title-small">本次变化</div>
              <div v-for="item in lastChanges" :key="item" class="change-row">{{ normalizePreflightText(item) }}</div>
            </div>

            <div class="drawer-list">
              <div v-for="item in sortedChecks" :key="item.key" class="drawer-item" :class="`item-${item.status.toLowerCase()}`">
                <div class="item-heading">
                  <div>
                    <div class="drawer-item-title">{{ item.label }}</div>
                    <div class="muted">{{ item.category || '平台接入' }}</div>
                  </div>
                  <el-tag size="small" :type="preflightTag(item.status)" effect="light">{{ preflightLabel(item.status) }}</el-tag>
                </div>
                <div class="field-block">{{ item.message }}</div>
                <div v-if="item.evidenceSource" class="field-block muted">证据：{{ item.evidenceSource }}</div>
                <div v-if="item.evidenceScope" class="field-block muted">范围：{{ item.evidenceScope }}</div>
                <template v-if="['FAIL', 'WARN'].includes(item.status)">
                  <div v-if="item.impact" class="field-block"><strong>影响：</strong>{{ item.impact }}</div>
                  <div class="field-block"><strong>处理：</strong>{{ item.action || item.suggestion }}</div>
                </template>
                <div v-else-if="item.status === 'PENDING'" class="field-block"><strong>后续：</strong>{{ item.suggestion || '系统将在对应场景自动验证。' }}</div>
                <div v-if="item.autoActionCommand" class="command-row"><span>{{ item.automationType === 'PLATFORM_SCRIPT' ? '平台服务器兜底命令' : '自动化命令' }}</span><el-button size="small" @click="copyText(item.autoActionCommand || '')">复制</el-button></div>
                <pre v-if="item.autoActionCommand" class="verify-command">{{ item.autoActionCommand }}</pre>
                <div v-if="item.verifyCommand" class="command-row"><span>验证命令</span><el-button size="small" @click="copyText(item.verifyCommand || '')">复制</el-button></div>
                <pre v-if="item.verifyCommand" class="verify-command">{{ item.verifyCommand }}</pre>
                <div class="drawer-actions">
                  <el-button v-if="item.actionEndpoint && item.actionAvailable && item.status === 'FAIL'" type="success" size="small" :loading="actionRunning" @click="runAutoFix(item)">{{ item.actionButtonLabel || '自动处理' }}</el-button>
                  <el-button v-if="item.route && ['FAIL', 'WARN'].includes(item.status)" type="primary" plain size="small" @click="goRoute(item.route)">{{ item.actionLabel || '去处理' }}</el-button>
                </div>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="安全与接入">
            <div v-if="preflight.securityAdvisories?.length" class="drawer-section first-section">
              <div class="section-title-small">安全建议</div>
              <div class="muted section-note">仅供治理参考，不影响运行状态。</div>
              <div class="drawer-list">
                <div v-for="item in preflight.securityAdvisories" :key="item.key" class="drawer-item">
                  <div class="drawer-item-title">{{ item.label }}</div>
                  <div class="field-block">{{ item.message }}</div>
                  <div v-if="item.suggestion" class="field-block"><strong>建议：</strong>{{ item.suggestion }}</div>
                </div>
              </div>
            </div>

            <div v-if="preflight.securityGroupChecklist?.rules?.length" class="drawer-section">
              <div class="section-title-small">网络安全建议</div>
              <div class="drawer-list">
                <div v-for="rule in preflight.securityGroupChecklist.rules" :key="`${rule.name}-${rule.port}`" class="drawer-item">
                  <div class="drawer-item-title">{{ rule.name }} · {{ rule.protocol }}/{{ rule.port }}</div>
                  <div class="field-block"><strong>建议来源：</strong>{{ rule.source }}</div>
                  <div class="field-block"><strong>建议：</strong>{{ rule.suggestion }}</div>
                  <div v-if="rule.risk" class="field-block"><strong>风险：</strong>{{ rule.risk }}</div>
                </div>
              </div>
              <div class="drawer-actions"><el-button size="small" @click="copyText(securityGroupChecklistText)">复制规则清单</el-button></div>
            </div>

            <div class="drawer-section">
              <div class="section-title-small">接入端口</div>
              <div v-if="preflight.requiredPorts?.length" class="drawer-list">
                <div v-for="item in preflight.requiredPorts" :key="`${item.name}-${item.host}-${item.port}`" class="drawer-item">
                  <div class="drawer-item-title">{{ item.name }} · {{ item.host }}:{{ item.port }}/{{ item.protocol }}</div>
                  <div class="field-block">{{ item.impact || item.reason }}</div>
                  <div v-if="item.verifyCommand" class="command-row"><span>验证命令</span><el-button size="small" @click="copyText(item.verifyCommand || '')">复制</el-button></div>
                  <pre v-if="item.verifyCommand" class="verify-command">{{ item.verifyCommand }}</pre>
                </div>
              </div>
              <el-empty v-else description="暂无接入端口信息" />
            </div>
          </el-tab-pane>

          <el-tab-pane label="检测历史">
            <div v-if="preflightHistory.length" class="history-list">
              <div v-for="item in preflightHistory" :key="item.snapshotId" class="history-row">
                <el-tag size="small" :type="preflightTag(item.status)" effect="light">{{ preflightLabel(item.status) }}</el-tag>
                <div class="history-main">
                  <div><strong>{{ item.checkSourceLabel }}</strong> · {{ formatTime(item.checkedAt || item.createdAt || '') }}</div>
                  <div class="muted">已确认异常 {{ item.blockingCount }} · 运行提醒 {{ item.warningCount }} · 待自动验证 {{ item.pendingCount || 0 }}</div>
                  <div v-if="item.changes?.length" class="history-changes">{{ item.changes.slice(0, 3).map(normalizePreflightText).join('；') }}</div>
                </div>
              </div>
            </div>
            <el-empty v-else description="暂无检测历史" />
          </el-tab-pane>
        </el-tabs>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listDashboardSummaries, prepareAgentImageAction } from '../api/platform'
import type { ControlPlanePreflight, ControlPlanePreflightCheck, DashboardSummary, PlatformActionResult } from '../types/api'
import { formatTime } from '../utils/dictionaries'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const detailVisible = ref(false)
const lastChanges = ref<string[]>([])
const actionRunning = ref(false)
const actionResult = ref<PlatformActionResult | null>(null)
const summary = ref<DashboardSummary>({ projectCount: 0, serverCount: 0, taskCount: 0, runningCount: 0, waitingCount: 0 })
const preflight = computed<ControlPlanePreflight | undefined>(() => summary.value.platformPreflight)
const preflightHistory = computed(() => summary.value.platformPreflightHistory || [])
const runtimeIssues = computed<ControlPlanePreflightCheck[]>(() => summary.value.runtimeIssues || [])
const overallStatus = computed<'PASS' | 'WARN' | 'FAIL'>(() => {
  if (preflight.value?.status === 'FAIL' || runtimeIssues.value.some((item) => item.status === 'FAIL')) return 'FAIL'
  if (preflight.value?.status === 'WARN' || runtimeIssues.value.some((item) => item.status === 'WARN')) return 'WARN'
  return 'PASS'
})
const cards = computed(() => [
  { title: '项目', value: summary.value.projectCount },
  { title: '执行节点', value: summary.value.serverCount },
  { title: '任务', value: summary.value.taskCount },
  { title: '运行中', value: summary.value.runningCount },
  { title: '等待资源', value: summary.value.waitingCount },
])
const problemChecks = computed<ControlPlanePreflightCheck[]>(() => (preflight.value?.checks || []).filter((item) => ['FAIL', 'WARN'].includes(item.status)))
const blockingProblems = computed(() => problemChecks.value.filter((item) => item.status === 'FAIL'))
const currentProblems = computed<ControlPlanePreflightCheck[]>(() => [...runtimeIssues.value, ...problemChecks.value])
const currentProblemCount = computed(() => currentProblems.value.length)
const topProblems = computed(() => [...currentProblems.value].sort((a, b) => statusWeight(a.status) - statusWeight(b.status)).slice(0, 4))
const sortedChecks = computed(() => [...(preflight.value?.checks || [])].sort((a, b) => statusWeight(a.status) - statusWeight(b.status)))
const autoFixCandidate = computed(() => blockingProblems.value.find((item) => item.actionEndpoint && item.actionAvailable && item.automationType === 'PLATFORM_SCRIPT'))
const securityGroupChecklistText = computed(() => {
  const checklist = preflight.value?.securityGroupChecklist
  if (!checklist?.rules?.length) return ''
  const lines = [checklist.title || '平台服务器安全组 / 防火墙规则清单']
  if (checklist.controlPlaneUrl) lines.push(`平台入口：${checklist.controlPlaneUrl}`)
  lines.push('')
  for (const rule of checklist.rules) {
    lines.push(`- ${rule.name}: ${rule.protocol}/${rule.port}`)
    lines.push(`  建议来源：${rule.source}`)
    lines.push(`  建议：${rule.suggestion}`)
    if (rule.risk) lines.push(`  风险：${rule.risk}`)
  }
  if (checklist.notes?.length) {
    lines.push('')
    for (const note of checklist.notes) lines.push(`备注：${note}`)
  }
  return lines.join('\n')
})
const platformStatusTitle = computed(() => {
  if (overallStatus.value === 'FAIL') return '平台存在运行异常'
  if (overallStatus.value === 'WARN') return '平台存在运行提醒'
  return '平台运行正常'
})
const platformStatusSummary = computed(() => {
  if (overallStatus.value === 'FAIL') return `${currentProblemCount.value} 项问题需要处理`
  if (overallStatus.value === 'WARN') return `${currentProblemCount.value} 项问题需要关注`
  return '当前未发现运行异常'
})

function statusWeight(status: string) { if (status === 'FAIL') return 0; if (status === 'WARN') return 1; if (status === 'PENDING') return 2; return 3 }
function preflightTag(status: string) { if (status === 'PASS') return 'success'; if (status === 'FAIL') return 'danger'; if (status === 'PENDING') return 'info'; return 'warning' }
function preflightLabel(status: string) { if (status === 'PASS') return '已验证'; if (status === 'FAIL') return '已确认异常'; if (status === 'PENDING') return '待自动验证'; return '运行提醒' }
function normalizePreflightText(value?: string) {
  return String(value || '')
    .replace(/阻断项/g, '必须处理项')
    .replace(/阻断/g, '已确认异常')
    .replace(/需确认项/g, '运行提醒')
    .replace(/需确认/g, '运行提醒')
    .replace(/待场景验证/g, '待自动验证')
    .replace(/Agent 容器/g, '执行组件容器')
    .replace(/Agent/g, '执行组件')
}
function comparePreflight(before?: ControlPlanePreflight, after?: ControlPlanePreflight) {
  if (!before || !after) return []
  const changes: string[] = []
  if (before.status !== after.status) changes.push(`总体状态：${preflightLabel(before.status)} -> ${preflightLabel(after.status)}`)
  if (before.blockingCount !== after.blockingCount) changes.push(`已确认异常：${before.blockingCount} -> ${after.blockingCount}`)
  if (before.warningCount !== after.warningCount) changes.push(`运行提醒：${before.warningCount} -> ${after.warningCount}`)
  if (before.pendingCount !== after.pendingCount) changes.push(`待自动验证：${before.pendingCount} -> ${after.pendingCount}`)
  const previous = new Map((before.checks || []).map((item) => [item.key, item]))
  for (const item of after.checks || []) {
    const old = previous.get(item.key)
    if (old && old.status !== item.status) changes.push(`${item.label}：${preflightLabel(old.status)} -> ${preflightLabel(item.status)}`)
  }
  return changes.slice(0, 6)
}
async function load(source: 'AUTO' | 'MANUAL' = 'AUTO') {
  const before = summary.value.platformPreflight
  loading.value = true
  try {
    const next = await listDashboardSummaries({ preflightSource: source })
    summary.value = next
    if (source === 'MANUAL') {
      lastChanges.value = comparePreflight(before, next.platformPreflight)
      const status = next.platformPreflight
      ElMessage.success(`检测完成：异常 ${(status?.blockingCount ?? 0) + (status?.warningCount ?? 0)}，待自动验证 ${status?.pendingCount ?? 0}${lastChanges.value.length ? '，状态有变化' : ''}`)
    }
  } finally {
    loading.value = false
  }
}
function goRoute(target: string) { if (target) router.push(target) }
async function copyText(text: string) {
  if (!text) return
  if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text)
  else {
    const el = document.createElement('textarea')
    el.value = text
    document.body.appendChild(el)
    el.select()
    document.execCommand('copy')
    document.body.removeChild(el)
  }
  ElMessage.success('已复制')
}
async function runAutoFix(item?: ControlPlanePreflightCheck) {
  const target = item || autoFixCandidate.value
  if (!target || !target.actionAvailable || target.status !== 'FAIL') {
    ElMessage.warning(target?.actionUnavailableReason || '当前问题不支持页面一键处理。')
    return
  }
  try {
    await ElMessageBox.confirm('平台将执行受控白名单动作，可能构建镜像、更新运行配置并短暂重启后端服务。确认继续？', target.actionButtonLabel || '自动处理', { type: 'warning', confirmButtonText: '确认执行', cancelButtonText: '取消' })
  } catch {
    return
  }
  actionRunning.value = true
  try {
    const result = await prepareAgentImageAction()
    actionResult.value = result
    detailVisible.value = true
    if (result.status === 'SUCCESS') {
      ElMessage.success(result.message || '自动处理完成，正在重新检测')
      await load('MANUAL')
    } else if (result.status === 'UNAVAILABLE') {
      ElMessage.warning(result.message || '当前部署暂不支持页面一键处理')
    } else {
      ElMessage.warning(result.message || '自动处理未完成，请查看详情')
    }
  } catch (error: any) {
    const data = error?.response?.data?.data
    if (data) actionResult.value = data
    detailVisible.value = true
    ElMessage.error(error?.response?.data?.message || '自动处理失败')
  } finally {
    actionRunning.value = false
  }
}
onMounted(() => { if (route.query.focus === 'platformPreflight') detailVisible.value = true; load('AUTO') })
</script>

<style scoped>
.dashboard-page { display: grid; gap: 16px; }
.metric-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; }
.metric-card { min-height: 92px; padding: 16px; border: 1px solid #edf1f5; border-radius: 14px; background: #fff; }
.metric-card span { color: #64748b; font-size: 13px; }
.metric-card strong { display: block; margin-top: 8px; color: #0f172a; font-size: 28px; line-height: 1; }
.health-card { display: flex; align-items: center; justify-content: space-between; gap: 18px; min-height: 112px; border: 1px solid #dcfce7; background: #fff; }
.health-warn { border-color: #fed7aa; }
.health-fail { border-color: #fecaca; }
.health-main { display: flex; align-items: flex-start; gap: 12px; min-width: 0; }
.status-dot { display: inline-block; flex: 0 0 auto; width: 10px; height: 10px; margin-top: 7px; border-radius: 50%; }
.dot-pass { background: #22c55e; }
.dot-warn { background: #f59e0b; }
.dot-fail { background: #ef4444; }
.health-title { color: #0f172a; font-size: 18px; font-weight: 800; }
.health-summary { margin-top: 5px; color: #475569; }
.health-meta { margin-top: 8px; color: #94a3b8; font-size: 12px; }
.health-actions { display: flex; gap: 8px; flex: 0 0 auto; }
.issues-card { padding-bottom: 10px; }
.issues-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 4px; }
.section-title-small { color: #0f172a; font-weight: 800; }
.issue-list { display: grid; }
.issue-row { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 10px; align-items: center; padding: 12px 0; border-top: 1px solid #eef2f7; }
.issue-indicator { width: 7px; height: 7px; border-radius: 50%; }
.issue-warn { background: #f59e0b; }
.issue-fail { background: #ef4444; }
.issue-title { color: #0f172a; font-weight: 700; }
.issue-message { margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.quiet-state { display: flex; align-items: center; gap: 8px; padding: 2px 4px; color: #64748b; font-size: 13px; }
.quiet-check { color: #22c55e; font-weight: 900; }
.drawer-overview { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; padding: 15px 16px; margin-bottom: 18px; border: 1px solid #dcfce7; border-radius: 14px; background: #fff; }
.drawer-warn { border-color: #fed7aa; }
.drawer-fail { border-color: #fecaca; }
.drawer-title-row { display: flex; align-items: center; gap: 9px; }
.drawer-title-row .status-dot { margin-top: 0; }
.drawer-title-row h3 { margin: 0 0 5px; }
.detail-tabs { margin-top: 4px; }
.drawer-list { display: grid; gap: 10px; }
.drawer-item { padding: 13px 14px; border: 1px solid #e2e8f0; border-radius: 14px; background: #fff; }
.item-fail { border-color: #fecaca; }
.item-warn { border-color: #fed7aa; }
.item-pending { border-color: #dbeafe; background: #f8fbff; }
.item-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 7px; }
.drawer-item-title { color: #0f172a; font-weight: 800; }
.field-block { margin-top: 7px; color: #475569; line-height: 1.6; }
.field-block strong { color: #111827; }
.drawer-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.command-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 10px; color: #111827; font-weight: 700; }
.verify-command { margin-top: 8px; padding: 9px 10px; border-radius: 10px; background: #111827; color: #e5e7eb; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; white-space: pre-wrap; word-break: break-all; }
.drawer-section { margin-top: 20px; }
.first-section { margin-top: 0; }
.section-note { margin: 5px 0 12px; }
.compact-change-box { margin-bottom: 12px; padding: 10px 12px; border-radius: 12px; background: #f8fafc; }
.change-row { padding: 5px 0; color: #475569; border-top: 1px solid #e5e7eb; }
.action-result { margin-bottom: 16px; padding: 12px; border: 1px solid #e2e8f0; border-radius: 14px; background: #f8fafc; }
.result-success { border-color: #bbf7d0; background: #f0fdf4; }
.result-unavailable, .result-failed { border-color: #fed7aa; background: #fff7ed; }
.mini-log { margin: 8px 0 0; max-height: 180px; overflow: auto; padding: 8px; border-radius: 10px; background: #111827; color: #e5e7eb; font-size: 12px; white-space: pre-wrap; }
.history-list { display: grid; gap: 10px; }
.history-row { display: flex; gap: 12px; align-items: flex-start; padding: 11px 12px; border: 1px solid #eef2f7; border-radius: 12px; background: #fff; }
.history-main { display: grid; gap: 4px; min-width: 0; }
.history-changes { color: #2563eb; font-size: 12px; }
@media (max-width: 1080px) { .metric-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 760px) { .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .health-card { align-items: flex-start; flex-direction: column; } .health-actions { width: 100%; } }
</style>

<template>
  <div class="dashboard-page">
    <div class="page-card overview-card">
      <div class="toolbar dashboard-toolbar">
        <div>
          <h3>运行总览</h3>
          <p class="muted">查看平台运行状态、任务概览和平台自检结果。</p>
        </div>
        <el-button :loading="loading" @click="load('AUTO')">刷新总览</el-button>
      </div>
      <el-row :gutter="16">
        <el-col v-for="item in cards" :key="item.title" :span="4">
          <el-card shadow="never" class="summary-card"><div class="muted">{{ item.title }}</div><h2>{{ item.value }}</h2></el-card>
        </el-col>
      </el-row>
    </div>

    <div v-if="preflight" class="page-card platform-check-card" :class="`platform-check-${preflight.status.toLowerCase()}`">
      <div class="platform-check-hero">
        <div class="status-orb" :class="`status-${preflight.status.toLowerCase()}`"><span>{{ preflightIcon }}</span></div>
        <div class="platform-check-main">
          <div class="section-kicker">平台自检</div>
          <h3>{{ preflightTitle }}</h3>
          <p>{{ preflight.summary }}</p>
          <div class="check-meta status-chip-grid">
            <div class="status-chip"><span class="chip-label">状态</span><el-tag :type="preflightTag(preflight.status)" effect="light">{{ preflightLabel(preflight.status) }}</el-tag></div>
            <div class="status-chip"><span class="chip-label">必须处理</span><strong>{{ preflight.blockingCount }}</strong></div>
            <div class="status-chip"><span class="chip-label">需确认</span><strong>{{ preflight.warningCount }}</strong></div>
            <div class="status-chip"><span class="chip-label">来源</span><strong>{{ preflight.checkSourceLabel || '页面自动检测' }}</strong></div>
            <div v-if="preflight.checkedAt" class="status-chip"><span class="chip-label">时间</span><strong>{{ formatTime(preflight.checkedAt) }}</strong></div>
          </div>
        </div>
        <div class="platform-check-actions">
          <el-button v-if="autoFixCandidate" type="success" :loading="actionRunning" @click="runAutoFix()">{{ autoFixCandidate.actionButtonLabel || '自动准备执行组件镜像' }}</el-button>
          <el-button type="primary" :loading="loading" @click="load('MANUAL')">重新检测</el-button>
          <el-button @click="detailVisible = true">查看详情</el-button>
        </div>
      </div>

      <div class="platform-check-summary">
        <div class="next-action-card">
          <div class="section-title-small">下一步动作</div>
          <template v-if="autoFixCandidate">
            <div class="action-problem-title">{{ autoFixCandidate.label }}</div>
            <div class="action-problem-line"><strong>影响：</strong>{{ autoFixCandidate.impact || autoFixCandidate.message }}</div>
            <div class="auto-action-box">
              <div><strong>推荐动作：</strong>{{ autoFixCandidate.actionButtonLabel || '自动准备执行组件镜像' }}</div>
              <div class="muted">当前部署已启用页面白名单动作，平台会执行受控动作；可能构建镜像、写入配置并短暂重启后端服务。</div>
              <div class="auto-buttons">
                <el-button type="success" :loading="actionRunning" @click="runAutoFix()">{{ autoFixCandidate.actionButtonLabel || '自动准备执行组件镜像' }}</el-button>
                <el-button v-if="autoFixCandidate.manualCommand || autoFixCandidate.autoActionCommand" @click="copyText(autoFixCandidate.manualCommand || autoFixCandidate.autoActionCommand || '')">复制兜底命令</el-button>
              </div>
            </div>
          </template>
          <template v-else-if="fallbackScriptCandidate">
            <div class="action-problem-title">{{ fallbackScriptCandidate.label }}</div>
            <div class="action-problem-line"><strong>影响：</strong>{{ fallbackScriptCandidate.impact || fallbackScriptCandidate.message }}</div>
            <div class="fallback-action-box">
              <div><strong>当前页面不能一键处理</strong></div>
              <div class="muted">{{ fallbackScriptCandidate.actionUnavailableReason || preflight.platformActionCapability?.reason || '页面白名单动作未启用。CI/CD 会在部署阶段自动处理；极端情况下可使用平台服务器兜底命令。' }}</div>
              <div v-if="fallbackScriptCandidate.manualCommand || fallbackScriptCandidate.autoActionCommand" class="command-row"><span>平台服务器兜底命令</span><el-button size="small" @click="copyText(fallbackScriptCandidate.manualCommand || fallbackScriptCandidate.autoActionCommand || '')">复制</el-button></div>
              <pre v-if="fallbackScriptCandidate.manualCommand || fallbackScriptCandidate.autoActionCommand" class="verify-command">{{ fallbackScriptCandidate.manualCommand || fallbackScriptCandidate.autoActionCommand }}</pre>
            </div>
          </template>
          <template v-else-if="preflight.status === 'WARN'">
            <div class="action-problem-title">平台服务器外部访问策略待确认</div>
            <div class="action-problem-line"><strong>下一步：</strong>{{ preflight.nextAction || '请确认云服务器安全组、防火墙和内置镜像仓库访问策略。' }}</div>
            <div class="security-checklist-box">
              <div><strong>推荐动作：</strong>复制平台服务器安全组规则清单，在云控制台和服务器防火墙中确认。</div>
              <div class="muted">当前状态是“需确认”，不是平台侧部署失败；平台无法在未授权情况下自动修改云安全组。</div>
              <div v-if="securityGroupChecklistText" class="command-row"><span>安全组规则清单</span><el-button size="small" @click="copyText(securityGroupChecklistText)">复制清单</el-button></div>
              <pre v-if="securityGroupChecklistText" class="verify-command verify-script">{{ securityGroupChecklistText }}</pre>
              <div class="auto-buttons">
                <el-button v-if="securityGroupChecklistText" type="primary" plain @click="copyText(securityGroupChecklistText)">复制清单</el-button>
                <el-button @click="detailVisible = true">查看确认项</el-button>
              </div>
            </div>
          </template>
          <div v-else class="node-verify-box"><strong>平台侧接入条件已就绪。</strong><div class="muted">{{ preflight.nextAction || '可以继续新增或重新接入执行节点。' }}</div></div>
          <div v-if="actionResult" class="action-result" :class="`result-${String(actionResult.status || '').toLowerCase()}`">
            <div><strong>{{ actionResult.status === 'SUCCESS' ? '自动处理完成' : (actionResult.status === 'UNAVAILABLE' ? '当前不能一键处理' : '自动处理结果') }}</strong>：{{ actionResult.message || actionResult.stage }}</div>
            <div v-if="actionResult.stage" class="muted">阶段：{{ actionResult.stage }}</div>
            <pre v-if="actionResult.logs?.length" class="mini-log">{{ actionResult.logs.slice(-12).join('\n') }}</pre>
            <div v-if="actionResult.manualCommand" class="command-row"><span>手动兜底命令</span><el-button size="small" @click="copyText(actionResult.manualCommand || '')">复制</el-button></div>
            <pre v-if="actionResult.manualCommand" class="verify-command">{{ actionResult.manualCommand }}</pre>
          </div>
          <div v-if="preflight.automationSummary" class="automation-pills">
            <el-tag v-if="preflight.automationSummary.pageAction" size="small" type="success" effect="light">页面一键可处理 {{ preflight.automationSummary.pageAction }} 项</el-tag>
            <el-tag v-if="preflight.automationSummary.ciCdOrServerScript" size="small" type="info" effect="light">CI/CD 或平台服务器兜底处理 {{ preflight.automationSummary.ciCdOrServerScript }} 项</el-tag>
            <el-tag v-if="preflight.automationSummary.cloudConsole" size="small" type="danger" effect="light">需云控制台处理 {{ preflight.automationSummary.cloudConsole }} 项</el-tag>
          </div>
        </div>
        <div class="problem-summary">
          <div class="section-title-small">当前重点事项</div>
          <div v-if="topProblems.length" class="mini-check-list">
            <div v-for="item in topProblems" :key="item.key" class="mini-check-row">
              <el-tag size="small" :type="preflightTag(item.status)" effect="light">{{ preflightLabel(item.status) }}</el-tag>
              <div>
                <div class="check-label">{{ item.label }}</div>
                <div class="muted">{{ item.impact || item.message }}</div>
              </div>
            </div>
            <div v-if="hiddenProblemCount > 0" class="more-problems">还有 {{ hiddenProblemCount }} 项，点击“查看详情”查看完整检查结果。</div>
          </div>
          <el-empty v-else description="平台接入基础条件已就绪" />
        </div>
      </div>

      <div v-if="lastChanges.length" class="change-card">
        <div class="section-title-small">本次检测变化</div>
        <div v-for="item in lastChanges" :key="item" class="change-row">{{ normalizePreflightText(item) }}</div>
      </div>
    </div>

    <div v-if="preflightHistory.length" class="page-card preflight-history-card">
      <div class="section-title-small">平台自检记录</div>
      <div class="history-list">
        <div v-for="item in preflightHistory" :key="item.snapshotId" class="history-row">
          <el-tag size="small" :type="preflightTag(item.status)" effect="light">{{ preflightLabel(item.status) }}</el-tag>
          <div class="history-main">
            <div><strong>{{ item.checkSourceLabel }}</strong> · {{ formatTime(item.checkedAt || item.createdAt || '') }}</div>
            <div class="muted">必须处理 {{ item.blockingCount }} · 需确认 {{ item.warningCount }} · {{ normalizePreflightText(item.summary) }}</div>
            <div v-if="item.changes?.length" class="history-changes">{{ item.changes.slice(0, 3).map(normalizePreflightText).join('；') }}</div>
          </div>
        </div>
      </div>
    </div>

    <el-drawer v-model="detailVisible" title="平台自检详情" size="620px" class="preflight-drawer">
      <template v-if="preflight">
        <div class="drawer-overview" :class="`drawer-${preflight.status.toLowerCase()}`">
          <div>
            <div class="section-kicker">{{ preflight.checkSourceLabel || '页面自动检测' }}</div>
            <h3>{{ preflightTitle }}</h3>
            <p>{{ preflight.summary }}</p>
          </div>
          <el-tag :type="preflightTag(preflight.status)" effect="light">{{ preflightLabel(preflight.status) }}</el-tag>
        </div>

        <div v-if="preflight.agentImageDigest || preflight.changes?.length" class="drawer-section">
          <div class="section-title-small">最近检测变化</div>
          <div v-if="preflight.agentImageDigest" class="field-block"><strong>执行组件镜像校验值：</strong>{{ preflight.agentImageDigest }}</div>
          <div v-for="item in preflight.changes || []" :key="item" class="change-row">{{ normalizePreflightText(item) }}</div>
        </div>

        <div v-if="preflight.securityGroupChecklist?.rules?.length" class="drawer-section">
          <div class="section-title-small">平台服务器安全组 / 防火墙规则</div>
          <div class="field-block">{{ preflight.securityGroupChecklist.summary }}</div>
          <div class="drawer-list">
            <div v-for="rule in preflight.securityGroupChecklist.rules" :key="`${rule.name}-${rule.port}`" class="drawer-item">
              <div class="drawer-item-title">{{ rule.name }}：{{ rule.protocol }}/{{ rule.port }}</div>
              <div class="field-block"><strong>建议来源：</strong>{{ rule.source }}</div>
              <div class="field-block"><strong>建议：</strong>{{ rule.suggestion }}</div>
              <div class="field-block"><strong>风险：</strong>{{ rule.risk }}</div>
            </div>
          </div>
          <div class="auto-buttons"><el-button size="small" @click="copyText(securityGroupChecklistText)">复制规则清单</el-button></div>
        </div>

        <div class="drawer-section">
          <div class="section-title-small">必须准备的端口</div>
          <div v-if="preflight.requiredPorts?.length" class="drawer-list">
            <div v-for="item in preflight.requiredPorts" :key="`${item.name}-${item.host}-${item.port}`" class="drawer-item">
              <div class="drawer-item-title">{{ item.name }}：{{ item.host }}:{{ item.port }}/{{ item.protocol }}</div>
              <div class="field-block"><strong>影响：</strong>{{ item.impact || item.reason }}</div>
              <div v-if="item.handler" class="field-block"><strong>处理方式：</strong>{{ item.handler }}</div>
              <div class="field-block"><strong>处理：</strong>{{ item.action }}</div>
              <div v-if="item.verifyCommand" class="command-row"><span>验证命令</span><el-button size="small" @click="copyText(item.verifyCommand || '')">复制</el-button></div>
              <pre v-if="item.verifyCommand" class="verify-command">{{ item.verifyCommand }}</pre>
            </div>
          </div>
          <el-empty v-else description="暂无需要准备的外部端口" />
        </div>

        <div class="drawer-section">
          <div class="section-title-small">检查项</div>
          <div class="drawer-list">
            <div v-for="item in preflight.checks" :key="item.key" class="drawer-item" :class="`item-${item.status.toLowerCase()}`">
              <div class="item-heading">
                <div>
                  <div class="drawer-item-title">{{ item.label }}</div>
                  <div class="muted">{{ item.category || '平台接入' }}</div>
                </div>
                <el-tag size="small" :type="preflightTag(item.status)" effect="light">{{ preflightLabel(item.status) }}</el-tag>
              </div>
              <div class="field-block"><strong>结果：</strong>{{ item.message }}</div>
              <div class="field-block"><strong>影响：</strong>{{ item.impact }}</div>
              <div v-if="item.handler" class="field-block"><strong>处理方式：</strong>{{ item.handler }}</div>
              <div v-if="item.status !== 'PASS'" class="field-block action-field"><strong>处理：</strong>{{ item.action || item.suggestion }}</div>
              <div v-if="item.autoActionCommand" class="command-row"><span>{{ item.automationType === 'PLATFORM_SCRIPT' ? '平台服务器兜底命令' : '自动化命令' }}</span><el-button size="small" @click="copyText(item.autoActionCommand || '')">复制</el-button></div>
              <pre v-if="item.autoActionCommand" class="verify-command">{{ item.autoActionCommand }}</pre>
              <div v-if="item.verifyCommand" class="command-row"><span>验证命令</span><el-button size="small" @click="copyText(item.verifyCommand || '')">复制</el-button></div>
              <pre v-if="item.verifyCommand" class="verify-command">{{ item.verifyCommand }}</pre>
              <div class="drawer-actions">
                <el-button v-if="item.actionEndpoint && item.actionAvailable && item.status === 'FAIL'" type="success" size="small" :loading="actionRunning" @click="runAutoFix(item)">{{ item.actionButtonLabel || '自动准备执行组件镜像' }}</el-button>
                <el-button v-if="item.route && item.status !== 'PASS'" class="route-button" type="primary" plain size="small" @click="goRoute(item.route)">{{ item.actionLabel || '去处理' }}</el-button>
              </div>
            </div>
          </div>
        </div>
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
const cards = computed(() => [
  { title: '项目数量', value: summary.value.projectCount },
  { title: '执行节点', value: summary.value.serverCount },
  { title: '任务数量', value: summary.value.taskCount },
  { title: '运行中', value: summary.value.runningCount },
  { title: '等待资源', value: summary.value.waitingCount },
])
const problemChecks = computed<ControlPlanePreflightCheck[]>(() => (preflight.value?.checks || []).filter((item) => item.status !== 'PASS'))
const blockingProblems = computed(() => problemChecks.value.filter((item) => item.status === 'FAIL'))
const topProblems = computed(() => [...problemChecks.value].sort((a, b) => statusWeight(a.status) - statusWeight(b.status)).slice(0, 6))
const hiddenProblemCount = computed(() => Math.max(0, problemChecks.value.length - topProblems.value.length))
const autoFixCandidate = computed(() => blockingProblems.value.find((item) => item.actionEndpoint && item.actionAvailable && item.automationType === 'PLATFORM_SCRIPT'))
const fallbackScriptCandidate = computed(() => blockingProblems.value.find((item) => item.automationType === 'PLATFORM_SCRIPT' && !item.actionAvailable))
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
const preflightTitle = computed(() => {
  if (!preflight.value) return '等待检测'
  if (preflight.value.status === 'FAIL') return '平台还有必须处理项'
  if (preflight.value.status === 'WARN') return '平台有需要确认的事项'
  return '平台接入条件已就绪'
})
const preflightIcon = computed(() => preflight.value?.status === 'PASS' ? '✓' : (preflight.value?.status === 'FAIL' ? '!' : 'i'))
function statusWeight(status: string) { if (status === 'FAIL') return 0; if (status === 'WARN') return 1; return 2 }
function preflightTag(status: string) { if (status === 'PASS') return 'success'; if (status === 'FAIL') return 'danger'; return 'warning' }
function preflightLabel(status: string) { if (status === 'PASS') return '通过'; if (status === 'FAIL') return '必须处理'; return '需确认' }
function normalizePreflightText(value?: string) {
  return String(value || '')
    .replace(/阻断项/g, '必须处理项')
    .replace(/阻断/g, '必须处理')
    .replace(/Agent 容器/g, '执行组件容器')
    .replace(/Agent/g, '执行组件')
}
function comparePreflight(before?: ControlPlanePreflight, after?: ControlPlanePreflight) {
  if (!before || !after) return []
  const changes: string[] = []
  if (before.status !== after.status) changes.push(`总体状态：${preflightLabel(before.status)} -> ${preflightLabel(after.status)}`)
  if (before.blockingCount !== after.blockingCount) changes.push(`必须处理项：${before.blockingCount} -> ${after.blockingCount}`)
  if (before.warningCount !== after.warningCount) changes.push(`需确认项：${before.warningCount} -> ${after.warningCount}`)
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
      ElMessage.success(`检测完成：必须处理 ${status?.blockingCount ?? 0}，需确认 ${status?.warningCount ?? 0}${lastChanges.value.length ? '，状态有变化' : '，状态无变化'}`)
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
    ElMessage.warning(target?.actionUnavailableReason || '当前检查项不适合页面一键处理，请按验证命令确认。')
    return
  }
  try {
    await ElMessageBox.confirm('平台将执行受控白名单动作准备执行组件镜像，可能会构建镜像、写入 .env 并短暂重启后端服务。确认继续？', target.actionButtonLabel || '自动准备执行组件镜像', { type: 'warning', confirmButtonText: '确认执行', cancelButtonText: '取消' })
  } catch {
    return
  }
  actionRunning.value = true
  try {
    const result = await prepareAgentImageAction()
    actionResult.value = result
    if (result.status === 'SUCCESS') {
      ElMessage.success(result.message || '自动处理完成，正在重新检测')
      await load('MANUAL')
    } else if (result.status === 'UNAVAILABLE') {
      ElMessage.warning(result.message || '当前部署暂不支持页面一键处理，请使用兜底命令')
    } else {
      ElMessage.warning(result.message || '自动处理未完成，请查看阶段日志')
    }
  } catch (error: any) {
    const data = error?.response?.data?.data
    if (data) actionResult.value = data
    ElMessage.error(error?.response?.data?.message || '自动处理失败')
  } finally {
    actionRunning.value = false
  }
}
onMounted(() => { if (route.query.focus === 'platformPreflight') detailVisible.value = true; load('AUTO') })
</script>
<style scoped>
.dashboard-page { display: grid; gap: 16px; }
.dashboard-toolbar { align-items: flex-start; justify-content: space-between; }
.dashboard-toolbar h3 { margin: 0 0 6px; }
.summary-card { border-radius: 14px; border-color: #eef2f7; }
.summary-card h2 { margin: 8px 0 0; color: #0f172a; }
.platform-check-card { position: relative; overflow: hidden; padding: 0; border: 1px solid #dbeafe; background: linear-gradient(135deg, #eff6ff 0%, #ffffff 58%, #f8fafc 100%); }
.platform-check-fail { border-color: #fecaca; background: linear-gradient(135deg, #fef2f2 0%, #fff 60%, #f8fafc 100%); }
.platform-check-warn { border-color: #fed7aa; background: linear-gradient(135deg, #fff7ed 0%, #fff 60%, #f8fafc 100%); }
.platform-check-hero { display: grid; grid-template-columns: auto 1fr auto; gap: 18px; align-items: center; padding: 22px; border-bottom: 1px solid rgba(148, 163, 184, 0.22); }
.status-orb { display: grid; place-items: center; width: 64px; height: 64px; border-radius: 22px; color: #fff; font-size: 30px; font-weight: 900; line-height: 1; box-shadow: 0 18px 36px rgba(15, 23, 42, 0.14); }
.status-pass { background: linear-gradient(135deg, #16a34a, #22c55e); }
.status-warn { background: linear-gradient(135deg, #f59e0b, #f97316); }
.status-fail { background: linear-gradient(135deg, #ef4444, #f97316); }
.section-kicker { color: #2563eb; font-size: 12px; font-weight: 800; letter-spacing: 0.08em; }
.platform-check-main h3 { margin: 4px 0 6px; color: #0f172a; font-size: 20px; }
.platform-check-main p { margin: 0; color: #475569; }
.check-meta { margin-top: 12px; color: #64748b; font-size: 12px; }
.status-chip-grid { display: flex; gap: 8px; align-items: stretch; flex-wrap: wrap; }
.status-chip { display: inline-flex; align-items: center; gap: 7px; min-height: 30px; padding: 5px 9px; border: 1px solid #e2e8f0; border-radius: 999px; background: rgba(255, 255, 255, 0.82); color: #334155; }
.status-chip .chip-label { color: #64748b; font-weight: 700; }
.status-chip strong { color: #0f172a; font-weight: 800; }
.platform-check-actions { display: flex; gap: 8px; align-items: center; }
.platform-check-summary { display: grid; grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.05fr); gap: 16px; padding: 18px 22px 22px; }
.next-action-card, .problem-summary, .change-card { border: 1px solid #e2e8f0; border-radius: 16px; background: rgba(255, 255, 255, 0.78); padding: 14px; box-shadow: 0 8px 22px rgba(15, 23, 42, 0.04); }
.next-action-card p { margin: 6px 0 8px; color: #0f172a; font-weight: 700; line-height: 1.6; }
.action-problem-title { margin: 4px 0 6px; color: #0f172a; font-size: 16px; font-weight: 900; }
.action-problem-line { color: #475569; line-height: 1.7; }
.action-problem-line strong { color: #111827; }
.automation-pills { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.auto-action-box { margin-top: 12px; padding: 13px; border: 1px solid #bbf7d0; border-radius: 14px; background: linear-gradient(135deg, #f0fdf4 0%, #ffffff 100%); }
.fallback-action-box { margin-top: 12px; padding: 13px; border: 1px solid #fed7aa; border-radius: 14px; background: linear-gradient(135deg, #fff7ed 0%, #ffffff 100%); }
.security-checklist-box, .node-verify-box { margin-top: 12px; padding: 13px; border: 1px solid #bfdbfe; border-radius: 14px; background: linear-gradient(135deg, #eff6ff 0%, #ffffff 100%); }
.auto-buttons { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.action-result { margin-top: 12px; padding: 12px; border-radius: 14px; border: 1px solid #e2e8f0; background: #f8fafc; }
.result-success { border-color: #bbf7d0; background: #f0fdf4; }
.result-unavailable, .result-failed { border-color: #fed7aa; background: #fff7ed; }
.mini-log { margin: 8px 0 0; max-height: 180px; overflow: auto; padding: 8px; border-radius: 10px; background: #111827; color: #e5e7eb; font-size: 12px; white-space: pre-wrap; }
.drawer-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.section-title-small { margin-bottom: 10px; color: #0f172a; font-weight: 800; }
.mini-check-list { display: grid; gap: 10px; }
.mini-check-row { display: grid; grid-template-columns: 58px 1fr; gap: 10px; align-items: flex-start; }
.check-label { margin-bottom: 3px; color: #111827; font-weight: 800; }
.change-card { margin: 0 22px 22px; }
.change-row { padding: 6px 0; color: #475569; border-top: 1px solid #e5e7eb; }
.drawer-overview { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 16px; border-radius: 16px; background: #eff6ff; border: 1px solid #dbeafe; margin-bottom: 16px; }
.drawer-fail { background: #fef2f2; border-color: #fecaca; }
.drawer-warn { background: #fff7ed; border-color: #fed7aa; }
.drawer-overview h3 { margin: 4px 0 6px; }
.drawer-overview p { margin: 0; color: #475569; }
.drawer-section { margin-top: 18px; }
.drawer-list { display: grid; gap: 12px; }
.drawer-item { padding: 14px; border: 1px solid #e2e8f0; border-radius: 16px; background: #fff; }
.item-fail { border-color: #fecaca; }
.item-warn { border-color: #fed7aa; }
.item-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 8px; }
.drawer-item-title { font-weight: 900; color: #0f172a; }
.field-block { margin-top: 8px; color: #475569; line-height: 1.6; }
.field-block strong { color: #111827; }
.action-field { color: #92400e; }
.command-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 10px; color: #111827; font-weight: 700; }
.verify-command { margin-top: 8px; padding: 9px 10px; border-radius: 10px; background: #111827; color: #e5e7eb; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; white-space: pre-wrap; word-break: break-all; }
.verify-script { line-height: 1.55; word-break: normal; }
.more-problems { padding: 9px 10px; border: 1px dashed #cbd5e1; border-radius: 12px; color: #475569; background: #f8fafc; font-size: 12px; }
.route-button { margin-top: 10px; }
@media (max-width: 980px) { .platform-check-hero, .platform-check-summary { grid-template-columns: 1fr; } .platform-check-actions { justify-content: flex-start; } .status-orb { width: 52px; height: 52px; border-radius: 18px; } }
.preflight-history-card { border: 1px solid #e5e7eb; }
.history-list { display: grid; gap: 10px; margin-top: 10px; }
.history-row { display: flex; gap: 12px; align-items: flex-start; padding: 10px 12px; border: 1px solid #eef2f7; border-radius: 12px; background: #fff; }
.history-main { display: grid; gap: 4px; }
.history-changes { color: #2563eb; font-size: 12px; }
</style>

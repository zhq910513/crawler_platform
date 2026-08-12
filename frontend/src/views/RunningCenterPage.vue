<template>
  <div class="running-center">
    <div class="hero-card">
      <div>
        <div class="breadcrumb-line">{{ summary?.company.companyName || '当前公司' }} > 项目 > 任务</div>
        <h2>{{ summary?.company.companyName || '公司' }}运行中心</h2>
        <p>按“公司 → 项目 → 任务”查看运行情况。项目部署不会自动启动任务，只有手动执行或启用调度后才会运行。</p>
      </div>
      <div class="hero-actions">
        <el-button :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" plain @click="router.push('/tasks')">查看任务编排</el-button>
      </div>
    </div>

    <el-row :gutter="14" class="metric-row">
      <el-col v-for="item in metrics" :key="item.title" :xs="12" :sm="8" :md="6" :lg="4">
        <div class="metric-card">
          <div class="metric-title">{{ item.title }}</div>
          <div class="metric-value" :class="item.className">{{ item.value }}</div>
          <div class="metric-hint">{{ item.hint }}</div>
        </div>
      </el-col>
    </el-row>

    <el-empty v-if="!loading && !projects.length" class="friendly-empty" description="还没有可查看的项目">
      <template #description>
        <div>当前公司还没有已接入项目。请先在项目版本中部署项目版本，部署完成后不会自动启动任务。</div>
      </template>
      <el-button type="primary" @click="router.push('/project-publish')">去项目发布</el-button>
    </el-empty>

    <el-skeleton v-if="loading" :rows="8" animated />

    <div v-else class="project-list">
      <el-card v-for="project in projects" :key="project.projectId" class="project-card" shadow="never">
        <div class="project-head" @click="toggleProject(project.projectId)">
          <div class="project-title-block">
            <div class="project-title-line">
              <h3>{{ project.projectName }}</h3>
              <el-tag :type="projectTag(project.projectStatus)" effect="light">{{ project.projectStatusText }}</el-tag>
              <el-tag v-if="project.singleTaskProject" type="info" effect="plain">单任务项目</el-tag>
              <el-tag v-else type="info" effect="plain">{{ project.taskCount }} 个任务</el-tag>
            </div>
            <div class="project-desc">{{ project.recentResultText }} · {{ project.projectAdvice }}</div>
          </div>
          <div class="project-stats">
            <span>运行中 {{ project.runningTaskCount }}</span>
            <span>异常 {{ project.failedTaskCount }}</span>
            <span>可用 {{ project.readyTaskCount }}</span>
            <el-button link type="primary">{{ expandedIds.has(project.projectId) ? '收起任务' : '查看任务' }}</el-button>
          </div>
        </div>

        <div v-if="project.singleTaskProject && project.tasks[0]" class="single-task-strip">
          <TaskRow :task="project.tasks[0]" :project="project" @detail="openTaskDetail" @run="manualRun" @logs="goRunLogs" @tasks="goTasks" />
        </div>

        <div v-else-if="expandedIds.has(project.projectId)" class="task-list">
          <TaskRow v-for="task in project.tasks" :key="task.taskId" :task="task" :project="project" @detail="openTaskDetail" @run="manualRun" @logs="goRunLogs" @tasks="goTasks" />
        </div>
      </el-card>
    </div>

    <el-drawer v-model="drawerVisible" size="720px" :with-header="false" class="task-detail-drawer">
      <template v-if="selectedTask && selectedProject">
        <div class="drawer-head">
          <div>
            <div class="breadcrumb-line">{{ summary?.company.companyName }} > {{ selectedProject.projectName }} > {{ selectedTask.taskName }}</div>
            <h2>{{ selectedTask.taskStateText }}</h2>
            <p>{{ selectedTask.advice }}</p>
          </div>
          <el-button circle plain @click="drawerVisible = false">×</el-button>
        </div>
        <div class="action-row">
          <el-button type="primary" :loading="runningTaskId === selectedTask.taskId" @click="manualRun(selectedTask)">手动执行</el-button>
          <el-button @click="goTasks(selectedTask)">返回任务编排</el-button>
          <el-button v-if="selectedTask.latestRun" @click="goRunLogs(selectedTask)">查看完整日志</el-button>
          <el-button v-if="selectedTask.server" @click="router.push('/servers')">查看服务器</el-button>
        </div>
        <el-tabs v-model="activeTab" class="detail-tabs" @tab-change="handleTabChange">
          <el-tab-pane label="概览" name="overview">
            <el-alert :title="overviewTitle" :description="selectedTask.advice" :type="alertType(selectedTask.stateLevel)" show-icon :closable="false" />
            <el-descriptions :column="1" border class="detail-desc">
              <el-descriptions-item label="项目">{{ selectedProject.projectName }}</el-descriptions-item>
              <el-descriptions-item label="任务">{{ selectedTask.taskName }}</el-descriptions-item>
              <el-descriptions-item label="任务状态">{{ selectedTask.taskStateText }}</el-descriptions-item>
              <el-descriptions-item label="最近执行">{{ selectedTask.latestRun ? zh(selectedTask.latestRun.runStatus) : '暂无执行记录' }}</el-descriptions-item>
              <el-descriptions-item label="失败摘要">{{ selectedTask.latestRun?.errorSummary || '-' }}</el-descriptions-item>
              <el-descriptions-item label="建议操作">{{ selectedTask.primaryAction }}</el-descriptions-item>
            </el-descriptions>
          </el-tab-pane>
          <el-tab-pane label="日志" name="logs">
            <div class="log-toolbar">
              <el-button size="small" :disabled="!selectedTask.latestRun" @click="loadRunLogs">刷新日志</el-button>
              <el-button size="small" :disabled="!selectedTask.latestRun" @click="goRunLogs(selectedTask)">打开执行记录</el-button>
            </div>
            <pre class="log-box">{{ logText || '暂无日志。任务执行后会在这里显示最近日志。' }}</pre>
          </el-tab-pane>
          <el-tab-pane label="事件" name="events">
            <el-empty v-if="!events.length" description="暂无生命周期事件" />
            <el-timeline v-else>
              <el-timeline-item v-for="event in events" :key="event.eventId" :timestamp="formatTime(event.createdAt)" :type="eventType(event.eventLevel)">
                <b>{{ zh(event.eventType) }}</b><span class="muted"> / {{ zh(event.stage) }}</span>
                <div>{{ event.message || '-' }}</div>
              </el-timeline-item>
            </el-timeline>
          </el-tab-pane>
          <el-tab-pane label="容器" name="container">
            <el-empty v-if="!selectedTask.container" description="暂无容器快照。新版 Agent 会在任务运行时回传 Docker 容器状态。" />
            <el-descriptions v-else :column="1" border>
              <el-descriptions-item label="容器状态">{{ zh(selectedTask.container.containerStatus) }}</el-descriptions-item>
              <el-descriptions-item label="容器名称">{{ selectedTask.container.containerName || '-' }}</el-descriptions-item>
              <el-descriptions-item label="容器 ID">{{ selectedTask.container.containerId || '-' }}</el-descriptions-item>
              <el-descriptions-item label="退出码">{{ selectedTask.container.exitCode ?? '-' }}</el-descriptions-item>
              <el-descriptions-item label="是否内存终止">{{ selectedTask.container.oomKilled ? '是' : '否' }}</el-descriptions-item>
              <el-descriptions-item label="内存使用">{{ selectedTask.container.memoryUsageMb ?? '-' }} MB</el-descriptions-item>
              <el-descriptions-item label="最近日志">{{ selectedTask.container.lastLogLine || '-' }}</el-descriptions-item>
            </el-descriptions>
          </el-tab-pane>
          <el-tab-pane label="服务器" name="server">
            <el-empty v-if="!selectedTask.server" description="本任务最近一次执行还没有绑定服务器" />
            <el-descriptions v-else :column="1" border>
              <el-descriptions-item label="节点名称">{{ selectedTask.server.serverName }}</el-descriptions-item>
              <el-descriptions-item label="节点状态">{{ zh(selectedTask.server.healthStatus) }} / {{ zh(selectedTask.server.capacityStatus) }}</el-descriptions-item>
              <el-descriptions-item label="Docker">{{ selectedTask.server.dockerStatus || '-' }}</el-descriptions-item>
              <el-descriptions-item label="CPU / 内存 / 磁盘">{{ pct(selectedTask.server.cpuUsage) }} / {{ pct(selectedTask.server.memoryUsage) }} / {{ pct(selectedTask.server.diskUsage) }}</el-descriptions-item>
              <el-descriptions-item label="并发槽位">{{ selectedTask.server.availableSlots ?? '-' }} / {{ selectedTask.server.maxSlots ?? '-' }}</el-descriptions-item>
              <el-descriptions-item label="最近错误">{{ selectedTask.server.lastError || '-' }}</el-descriptions-item>
            </el-descriptions>
          </el-tab-pane>
          <el-tab-pane label="历史记录" name="history">
            <el-button :disabled="!selectedTask.latestRun" @click="goRunLogs(selectedTask)">查看执行记录</el-button>
            <p class="muted">更多历史记录请进入执行记录页面，系统会自动按当前任务筛选。</p>
          </el-tab-pane>
        </el-tabs>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, ref } from 'vue'
import { ElButton, ElMessage, ElTag } from 'element-plus'
import { useRouter } from 'vue-router'
import { createRun, getRunningCenter, getRunLogTail, listRunEvents } from '../api/platform'
import type { RunningCenterProject, RunningCenterSummary, RunningCenterTask, RunEvent } from '../types/api'
import { formatTime, zh } from '../utils/dictionaries'

const router = useRouter()
const loading = ref(false)
const summary = ref<RunningCenterSummary | null>(null)
const expandedIds = ref<Set<number>>(new Set())
const drawerVisible = ref(false)
const selectedProject = ref<RunningCenterProject | null>(null)
const selectedTask = ref<RunningCenterTask | null>(null)
const activeTab = ref('overview')
const events = ref<RunEvent[]>([])
const logText = ref('')
const runningTaskId = ref<number | null>(null)

const projects = computed(() => summary.value?.projects || [])
const metrics = computed(() => {
  const o = summary.value?.overview || { projectCount: 0, taskCount: 0, runningCount: 0, failedCount: 0, readyCount: 0, onlineServerCount: 0, issueServerCount: 0 }
  return [
    { title: '项目', value: o.projectCount, hint: '当前公司项目', className: '' },
    { title: '任务', value: o.taskCount, hint: '项目下任务', className: '' },
    { title: '运行中', value: o.runningCount, hint: '正在执行', className: 'primary' },
    { title: '异常', value: o.failedCount, hint: '需要处理', className: o.failedCount ? 'danger' : '' },
    { title: '在线节点', value: o.onlineServerCount, hint: '可承载任务', className: 'success' },
    { title: '节点风险', value: o.issueServerCount, hint: '资源或健康异常', className: o.issueServerCount ? 'warning' : '' },
  ]
})
const overviewTitle = computed(() => selectedTask.value ? `${selectedTask.value.taskName}：${selectedTask.value.taskStateText}` : '任务详情')

const TaskRow = defineComponent({
  name: 'TaskRow',
  props: { task: { type: Object, required: true }, project: { type: Object, required: true } },
  emits: ['detail', 'run', 'logs', 'tasks'],
  setup(props, { emit }) {
    return () => {
      const task = props.task as RunningCenterTask
      return h('div', { class: 'task-row' }, [
        h('div', { class: 'task-main' }, [
          h('div', { class: 'task-title' }, [task.taskName, h(ElTag, { type: tagType(task.stateLevel), effect: 'light', size: 'small' }, () => task.taskStateText)]),
          h('div', { class: 'task-subtitle' }, task.advice),
        ]),
        h('div', { class: 'task-meta' }, [
          h('span', `容器：${task.container ? zh(task.container.containerStatus) : '暂无'}`),
          h('span', `节点：${task.server?.serverName || '-'}`),
          h('span', `最近：${task.latestRun ? zh(task.latestRun.runStatus) : '暂无'}`),
        ]),
        h('div', { class: 'task-actions' }, [
          h(ElButton, { size: 'small', type: 'primary', plain: true, onClick: () => emit('detail', task, props.project) }, () => '查看详情'),
          h(ElButton, { size: 'small', onClick: () => emit('run', task) }, () => '手动执行'),
          h(ElButton, { size: 'small', onClick: () => emit('tasks', task) }, () => task.primaryAction || '去处理'),
        ]),
      ])
    }
  },
})

function tagType(level: string) { return level === 'danger' ? 'danger' : level === 'warning' ? 'warning' : level === 'success' ? 'success' : level === 'primary' ? 'primary' : 'info' }
function projectTag(status: string) { if (status === 'HAS_ISSUE') return 'danger'; if (status === 'RUNNING') return 'warning'; if (status === 'NORMAL') return 'success'; return 'info' }
function alertType(level: string) { const t = tagType(level); return (t === 'danger' ? 'error' : t === 'success' || t === 'warning' ? t : 'info') as 'success' | 'warning' | 'info' | 'error' }
function eventType(level: string) { if (level === 'ERROR' || level === 'CRITICAL') return 'danger'; if (level === 'WARN' || level === 'WARNING') return 'warning'; return 'primary' }
function pct(value?: number | null) { return value === null || value === undefined ? '-' : `${Number(value).toFixed(1)}%` }
function toggleProject(projectId: number) { const next = new Set(expandedIds.value); next.has(projectId) ? next.delete(projectId) : next.add(projectId); expandedIds.value = next }
async function load() { loading.value = true; try { summary.value = await getRunningCenter(); const multi = summary.value.projects.find((p) => !p.singleTaskProject); if (multi) expandedIds.value = new Set([multi.projectId]) } finally { loading.value = false } }
async function manualRun(task: RunningCenterTask) { runningTaskId.value = task.taskId; try { await createRun(task.taskId); ElMessage.success('已创建手动执行，请在详情或执行记录中查看进度'); await load() } finally { runningTaskId.value = null } }
function openTaskDetail(task: RunningCenterTask, project: RunningCenterProject) { selectedTask.value = task; selectedProject.value = project; activeTab.value = 'overview'; events.value = []; logText.value = ''; drawerVisible.value = true }
function goTasks(task: RunningCenterTask) { router.push({ path: '/tasks', query: { taskId: task.taskId } }) }
function goRunLogs(task: RunningCenterTask) { if (task.latestRun?.runId) router.push({ path: '/runs', query: { runId: task.latestRun.runId, taskId: task.taskId } }) }
async function handleTabChange() { if (activeTab.value === 'events') await loadEvents(); if (activeTab.value === 'logs') await loadRunLogs() }
async function loadEvents() { if (!selectedTask.value?.latestRun?.runId) return; events.value = await listRunEvents(selectedTask.value.latestRun.runId) }
async function loadRunLogs() { if (!selectedTask.value?.latestRun?.runId) return; const tail = await getRunLogTail(selectedTask.value.latestRun.runId, { afterSeq: 0, limit: 200 }); logText.value = tail.chunks.map((chunk) => chunk.content).join('\n') }
onMounted(load)
</script>

<style scoped>
.running-center { display: flex; flex-direction: column; gap: 16px; }
.hero-card { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 24px 26px; border-radius: 20px; background: linear-gradient(135deg, #eff6ff 0%, #ffffff 58%, #f8fafc 100%); border: 1px solid #e2e8f0; box-shadow: 0 16px 40px rgba(15, 23, 42, 0.06); }
.hero-card h2 { margin: 6px 0 8px; font-size: 24px; color: #0f172a; }
.hero-card p { margin: 0; color: #64748b; }
.breadcrumb-line { color: #64748b; font-size: 13px; }
.hero-actions { display: flex; gap: 10px; white-space: nowrap; }
.metric-row { margin: 0 !important; }
.metric-card { min-height: 96px; padding: 16px; border: 1px solid #e2e8f0; border-radius: 18px; background: #fff; box-shadow: 0 12px 26px rgba(15, 23, 42, 0.04); }
.metric-title { color: #64748b; font-size: 13px; }
.metric-value { margin-top: 8px; font-size: 28px; font-weight: 800; color: #0f172a; }
.metric-value.primary { color: #2563eb; } .metric-value.success { color: #059669; } .metric-value.warning { color: #d97706; } .metric-value.danger { color: #dc2626; }
.metric-hint { margin-top: 5px; color: #94a3b8; font-size: 12px; }
.project-list { display: flex; flex-direction: column; gap: 14px; }
.project-card { border-radius: 18px; border: 1px solid #e2e8f0; }
.project-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; cursor: pointer; }
.project-title-block { min-width: 0; }
.project-title-line { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.project-title-line h3 { margin: 0; color: #111827; font-size: 18px; }
.project-desc { margin-top: 8px; color: #64748b; font-size: 13px; }
.project-stats { display: flex; align-items: center; gap: 12px; color: #64748b; font-size: 13px; white-space: nowrap; }
.single-task-strip, .task-list { margin-top: 16px; padding-top: 14px; border-top: 1px solid #eef2f7; }
.task-list { display: flex; flex-direction: column; gap: 10px; }
:deep(.task-row) { display: grid; grid-template-columns: 1.4fr 1fr auto; align-items: center; gap: 14px; padding: 14px; border: 1px solid #e5e7eb; border-radius: 14px; background: #f8fafc; }
:deep(.task-title) { display: flex; align-items: center; gap: 8px; font-weight: 700; color: #111827; }
:deep(.task-subtitle) { margin-top: 5px; color: #64748b; font-size: 13px; }
:deep(.task-meta) { display: flex; flex-direction: column; gap: 4px; color: #64748b; font-size: 13px; }
:deep(.task-actions) { display: flex; gap: 6px; }
.drawer-head { display: flex; justify-content: space-between; gap: 16px; padding: 22px 24px 14px; border-bottom: 1px solid #e5e7eb; }
.drawer-head h2 { margin: 6px 0 6px; color: #111827; }
.drawer-head p { margin: 0; color: #64748b; }
.action-row { display: flex; gap: 8px; padding: 14px 24px; border-bottom: 1px solid #eef2f7; }
.detail-tabs { padding: 0 24px 24px; }
.detail-desc { margin-top: 16px; }
.log-toolbar { margin-bottom: 10px; }
.log-box { min-height: 300px; max-height: 520px; overflow: auto; padding: 12px; color: #d1d5db; background: #111827; border-radius: 12px; white-space: pre-wrap; word-break: break-word; }
.friendly-empty { padding: 48px; border: 1px dashed #cbd5e1; border-radius: 18px; background: #fff; }
.muted { color: #64748b; }
@media (max-width: 1100px) { :deep(.task-row) { grid-template-columns: 1fr; } .project-head { align-items: flex-start; flex-direction: column; } .project-stats { flex-wrap: wrap; } }
</style>

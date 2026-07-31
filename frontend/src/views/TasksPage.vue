<template>
  <div class="page-card">
    <div class="toolbar">
      <el-select v-if="sessionState.user?.isSuperAdmin" v-model="companyId" placeholder="选择公司" style="width:220px" @change="loadProjectsForCompany">
        <el-option v-for="company in companies" :key="company.companyId" :label="company.companyName" :value="company.companyId" />
      </el-select>
      <span v-else class="muted">当前公司：{{ currentCompanyName }}</span>
      <el-select v-model="projectId" placeholder="选择项目" style="width:260px" @change="loadAllForProject">
        <el-option v-for="project in projects" :key="project.projectId" :label="`${project.projectName}（${project.projectCode}）`" :value="project.projectId" />
      </el-select>
      <el-button @click="loadAllForProject">刷新</el-button>
    </div>

    <h3>项目任务目录</h3>
    <el-table :data="definitions" border :row-class-name="definitionRowClass">
      <el-table-column label="任务名称" prop="taskName" />
      <el-table-column label="定义键" prop="definitionKey" />
      <el-table-column label="入口模块" prop="entryModule" />
      <el-table-column label="入口函数" prop="entryFunction" />
      <el-table-column label="建议调度" prop="suggestedCron" />
      <el-table-column label="执行方式"><template #default="s">{{ zh(s.row.executionMode) }}</template></el-table-column>
      <el-table-column label="状态"><template #default="s">{{ zh(s.row.definitionStatus) }}</template></el-table-column>
      <el-table-column label="操作" width="120"><template #default="s"><el-button size="small" :disabled="s.row.definitionStatus !== 'AVAILABLE'" @click="openCreate(s.row)">创建任务</el-button></template></el-table-column>
    </el-table>

    <h3>正式任务</h3>
    <el-table :data="tasks" border>
      <el-table-column label="任务名称" prop="taskName" min-width="180" />
      <el-table-column label="任务编码" prop="taskCode" min-width="140" />
      <el-table-column label="调度时间" min-width="180"><template #default="s">{{ scheduleText(s.row) }}</template></el-table-column>
      <el-table-column label="下次运行" min-width="170"><template #default="s">{{ s.row.nextRunAt || '-' }}</template></el-table-column>
      <el-table-column label="执行方式"><template #default="s">{{ zh(s.row.executionMode) }}</template></el-table-column>
      <el-table-column label="运行模式"><template #default="s">{{ zh(s.row.runtimeMode) }}</template></el-table-column>
      <el-table-column label="任务组"><template #default="s">{{ s.row.taskGroup || '-' }}</template></el-table-column>
      <el-table-column label="幂等策略"><template #default="s">{{ zh(s.row.idempotencyPolicy) }}</template></el-table-column>
      <el-table-column label="状态"><template #default="s">{{ zh(s.row.status) }}</template></el-table-column>
      <el-table-column label="操作" width="240"><template #default="s"><el-button size="small" type="primary" @click="manualRun(s.row.taskId)">手动执行</el-button><el-button size="small" @click="openSchedule(s.row)">修改调度</el-button></template></el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="从任务目录创建正式任务" width="760px">
      <el-form label-position="top">
        <el-form-item label="任务编码"><el-input v-model="form.taskCode" /></el-form-item>
        <el-form-item label="任务名称"><el-input v-model="form.taskName" /></el-form-item>
        <el-form-item label="任务状态"><el-select v-model="form.status"><el-option label="草稿" value="DRAFT" /><el-option label="启用" value="ENABLED" /></el-select></el-form-item>
        <el-form-item label="调度类型"><el-select v-model="form.scheduleType"><el-option label="手动" value="MANUAL" /><el-option label="定时" value="CRON" /></el-select></el-form-item>
        <el-form-item v-if="form.scheduleType === 'CRON'" label="Cron 表达式"><el-input v-model="form.cronExpression" placeholder="5 段格式：分钟 小时 日 月 星期" /></el-form-item>
        <el-form-item label="调度状态"><el-select v-model="form.scheduleStatus"><el-option label="暂停" value="PAUSED" /><el-option label="启用" value="ENABLED" /></el-select></el-form-item>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="运行模式"><el-select v-model="form.runtimeMode"><el-option label="共享环境隔离容器" value="SHARED_ENV_ISOLATED" /><el-option label="常驻 Worker 池（预留）" value="WORKER_POOL" /><el-option label="独占容器" value="DEDICATED_CONTAINER" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="IO 类型"><el-select v-model="form.ioClass"><el-option label="普通" value="NORMAL" /><el-option label="高 IO" value="HIGH" /><el-option label="低 IO" value="LOW" /></el-select></el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8"><el-form-item label="任务组"><el-input v-model="form.taskGroup" placeholder="如 api/browser/download/login" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="任务最大并发"><el-input-number v-model="form.taskMaxConcurrency" :min="1" :max="1000" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="任务组最大并发"><el-input-number v-model="form.groupMaxConcurrency" :min="1" :max="1000" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8"><el-form-item label="独占运行"><el-switch v-model="form.exclusiveMode" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="共享内存 MB"><el-input-number v-model="form.shmSizeMb" :min="16" :max="65536" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="日志上限 MB"><el-input-number v-model="form.logLimitMb" :min="1" :max="10240" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="资源锁"><el-input v-model="locksText" placeholder="用逗号分隔，如 account:amazon_us,profile:main" /></el-form-item>
        <el-form-item label="服务器限制"><el-select v-model="form.serverIds" multiple clearable placeholder="默认使用项目执行服务器池"><el-option v-for="server in projectServers" :key="server.serverId" :label="server.serverName || String(server.serverId)" :value="server.serverId" /></el-select></el-form-item>
        <el-form-item label="任务参数 JSON"><el-input v-model="paramsText" type="textarea" :rows="5" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" @click="saveTask">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="scheduleVisible" title="修改调度时间" width="820px">
      <el-alert title="平台使用 5 段 Cron：分钟 小时 日 月 星期。暂不支持秒、年、?、L、W、# 等 Quartz 语法。" type="info" show-icon :closable="false" />
      <el-form label-position="top" class="schedule-form">
        <el-row :gutter="16">
          <el-col :span="8"><el-form-item label="调度状态"><el-select v-model="scheduleForm.scheduleStatus"><el-option label="启用" value="ENABLED" /><el-option label="暂停" value="PAUSED" /><el-option label="停用" value="DISABLED" /></el-select></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="调度类型"><el-select v-model="scheduleForm.scheduleType"><el-option label="手动" value="MANUAL" /><el-option label="定时" value="CRON" /></el-select></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="重叠策略"><el-select v-model="scheduleForm.overlapPolicy"><el-option label="排队等待" value="QUEUE" /><el-option label="跳过新触发" value="SKIP" /><el-option label="允许并发" value="CONCURRENT" /><el-option label="取消旧任务" value="CANCEL_OLD" /></el-select></el-form-item></el-col>
        </el-row>
        <template v-if="scheduleForm.scheduleType === 'CRON'">
          <el-form-item label="快捷设置">
            <el-radio-group v-model="scheduleMode" @change="applyScheduleMode">
              <el-radio-button label="EVERY_N_MINUTES">每 N 分钟</el-radio-button>
              <el-radio-button label="EVERY_N_HOURS">每 N 小时</el-radio-button>
              <el-radio-button label="DAILY">每天</el-radio-button>
              <el-radio-button label="WEEKLY">每周</el-radio-button>
              <el-radio-button label="MONTHLY">每月</el-radio-button>
              <el-radio-button label="ADVANCED">高级 Cron</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-row v-if="scheduleMode === 'EVERY_N_MINUTES'" :gutter="16"><el-col :span="8"><el-form-item label="间隔分钟"><el-input-number v-model="intervalMinutes" :min="5" :max="1440" @change="applyScheduleMode" /></el-form-item></el-col></el-row>
          <el-row v-if="scheduleMode === 'EVERY_N_HOURS'" :gutter="16"><el-col :span="8"><el-form-item label="间隔小时"><el-input-number v-model="intervalHours" :min="1" :max="24" @change="applyScheduleMode" /></el-form-item></el-col></el-row>
          <el-row v-if="['DAILY','WEEKLY','MONTHLY'].includes(scheduleMode)" :gutter="16">
            <el-col v-if="scheduleMode === 'WEEKLY'" :span="8"><el-form-item label="星期"><el-select v-model="weekday" @change="applyScheduleMode"><el-option v-for="day in weekdayOptions" :key="day.value" :label="day.label" :value="day.value" /></el-select></el-form-item></el-col>
            <el-col v-if="scheduleMode === 'MONTHLY'" :span="8"><el-form-item label="日期"><el-input-number v-model="monthDay" :min="1" :max="31" @change="applyScheduleMode" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="时间"><el-time-picker v-model="dayTime" format="HH:mm" value-format="HH:mm" @change="applyScheduleMode" /></el-form-item></el-col>
          </el-row>
          <el-form-item label="Cron 表达式"><el-input v-model="scheduleForm.cronExpression" @input="scheduleMode = 'ADVANCED'" /></el-form-item>
          <el-form-item label="时区"><el-input v-model="scheduleForm.scheduleTimezone" /></el-form-item>
          <el-button @click="loadCronPreview">校验并预览最近 5 次</el-button>
          <div class="preview-box"><div class="muted">最近 5 次预计执行时间</div><ul><li v-for="item in cronPreview" :key="item">{{ item }}</li></ul></div>
        </template>
      </el-form>
      <template #footer><el-button @click="scheduleVisible = false">取消</el-button><el-button type="primary" @click="saveSchedule">保存调度</el-button></template>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createRun, createTask, listCompanies, listProjectServers, listProjects, listTaskDefinitions, listTasks, previewCronExpression, updateTaskSchedule } from '../api/platform'
import { sessionState } from '../stores/session'
import type { Company, Project, ProjectServer, ScheduleUpdateRequest, Task, TaskCreateRequest, TaskDefinition } from '../types/api'
import { zh } from '../utils/dictionaries'

const companies = ref<Company[]>([])
const projects = ref<Project[]>([])
const projectServers = ref<ProjectServer[]>([])
const definitions = ref<TaskDefinition[]>([])
const tasks = ref<Task[]>([])
const companyId = ref<number | undefined>(undefined)
const projectId = ref<number | undefined>(undefined)
const dialogVisible = ref(false)
const scheduleVisible = ref(false)
const paramsText = ref('{}')
const locksText = ref('')
const selectedTask = ref<Task | null>(null)
const cronPreview = ref<string[]>([])
const currentCompanyName = computed(() => companies.value.find((item) => item.companyId === sessionState.user?.companyId)?.companyName || '归属公司')
const form = reactive<TaskCreateRequest>({ definitionId: 0, taskCode: '', taskName: '', parameters: {}, status: 'DRAFT', imagePolicy: 'RELEASE_CHANNEL', releaseChannel: 'stable', scheduleType: 'MANUAL', cronExpression: '', scheduleStatus: 'PAUSED', scheduleTimezone: 'Asia/Shanghai', overlapPolicy: 'QUEUE', serverIds: [], runtimeMode: 'SHARED_ENV_ISOLATED', taskGroup: 'default', taskMaxConcurrency: 1, groupMaxConcurrency: 4, exclusiveMode: false, ioClass: 'NORMAL', shmSizeMb: 64, logLimitMb: 50, resourceLocks: [] })
const scheduleForm = reactive<ScheduleUpdateRequest>({ scheduleStatus: 'PAUSED', scheduleType: 'MANUAL', cronExpression: '', scheduleTimezone: 'Asia/Shanghai', overlapPolicy: 'QUEUE', scheduleConfig: {}, scheduleLabel: '' })
const scheduleMode = ref('DAILY')
const intervalMinutes = ref(30)
const intervalHours = ref(1)
const weekday = ref(1)
const monthDay = ref(1)
const dayTime = ref('08:00')
const weekdayOptions = [{ label: '周一', value: 1 }, { label: '周二', value: 2 }, { label: '周三', value: 3 }, { label: '周四', value: 4 }, { label: '周五', value: 5 }, { label: '周六', value: 6 }, { label: '周日', value: 0 }]

async function loadCompaniesAndProjects() { companies.value = await listCompanies(); companyId.value = sessionState.user?.isSuperAdmin ? (companyId.value || companies.value[0]?.companyId) : sessionState.user?.companyId || undefined; await loadProjectsForCompany() }
async function loadProjectsForCompany() { projects.value = await listProjects(companyId.value); projectId.value = projects.value[0]?.projectId; await loadAllForProject() }
async function loadAllForProject() { if (!projectId.value) return; definitions.value = await listTaskDefinitions(projectId.value); tasks.value = await listTasks({ projectId: projectId.value }); projectServers.value = await listProjectServers(projectId.value) }
function definitionRowClass({ row }: { row: TaskDefinition }) { return row.definitionStatus === 'AVAILABLE' ? '' : 'disabled-row' }
function openCreate(row: TaskDefinition) { form.definitionId = row.definitionId; form.taskCode = row.definitionKey; form.taskName = row.taskName; form.cronExpression = row.suggestedCron || ''; form.scheduleType = row.suggestedCron ? 'CRON' : 'MANUAL'; form.scheduleStatus = 'PAUSED'; form.scheduleTimezone = 'Asia/Shanghai'; form.overlapPolicy = 'QUEUE'; form.serverIds = []; form.runtimeMode = row.runtimeMode || 'SHARED_ENV_ISOLATED'; form.taskGroup = row.taskGroup || 'default'; form.taskMaxConcurrency = row.taskMaxConcurrency || 1; form.groupMaxConcurrency = row.groupMaxConcurrency || 4; form.exclusiveMode = row.exclusiveMode || false; form.ioClass = row.ioClass || 'NORMAL'; form.shmSizeMb = row.shmSizeMb || 64; form.logLimitMb = row.logLimitMb || 50; locksText.value = (row.resourceLocks || []).join(','); paramsText.value = JSON.stringify(row.defaultParams || {}, null, 2); dialogVisible.value = true }
async function saveTask() { form.parameters = JSON.parse(paramsText.value || '{}'); form.resourceLocks = locksText.value.split(',').map((item) => item.trim()).filter(Boolean); await createTask(form); dialogVisible.value = false; ElMessage.success('正式任务已创建'); await loadAllForProject() }
async function manualRun(taskId: number) { await createRun(taskId); ElMessage.success('已创建运行实例') }
function scheduleText(task: Task) { if (task.scheduleType !== 'CRON') return '手动执行'; return task.scheduleLabel || task.cronExpression || '-' }
function openSchedule(task: Task) { selectedTask.value = task; scheduleForm.scheduleStatus = task.scheduleStatus || 'PAUSED'; scheduleForm.scheduleType = task.scheduleType || 'MANUAL'; scheduleForm.cronExpression = task.cronExpression || '0 8 * * *'; scheduleForm.scheduleTimezone = task.scheduleTimezone || 'Asia/Shanghai'; scheduleForm.overlapPolicy = task.overlapPolicy || 'QUEUE'; scheduleForm.scheduleConfig = task.scheduleConfig || {}; scheduleForm.scheduleLabel = task.scheduleLabel || ''; cronPreview.value = []; scheduleVisible.value = true; if (scheduleForm.scheduleType === 'CRON') void loadCronPreview() }
function applyScheduleMode() { const [hour, minute] = dayTime.value.split(':'); if (scheduleMode.value === 'EVERY_N_MINUTES') { scheduleForm.cronExpression = `*/${intervalMinutes.value} * * * *`; scheduleForm.scheduleConfig = { mode: 'EVERY_N_MINUTES', intervalMinutes: intervalMinutes.value }; scheduleForm.scheduleLabel = `每 ${intervalMinutes.value} 分钟执行一次` } else if (scheduleMode.value === 'EVERY_N_HOURS') { scheduleForm.cronExpression = `0 */${intervalHours.value} * * *`; scheduleForm.scheduleConfig = { mode: 'EVERY_N_HOURS', intervalHours: intervalHours.value }; scheduleForm.scheduleLabel = `每 ${intervalHours.value} 小时执行一次` } else if (scheduleMode.value === 'DAILY') { scheduleForm.cronExpression = `${Number(minute)} ${Number(hour)} * * *`; scheduleForm.scheduleConfig = { mode: 'DAILY', time: dayTime.value }; scheduleForm.scheduleLabel = `每天 ${dayTime.value} 执行` } else if (scheduleMode.value === 'WEEKLY') { scheduleForm.cronExpression = `${Number(minute)} ${Number(hour)} * * ${weekday.value}`; scheduleForm.scheduleConfig = { mode: 'WEEKLY', weekday: weekday.value, time: dayTime.value }; scheduleForm.scheduleLabel = `每周${weekdayOptions.find((item) => item.value === weekday.value)?.label.replace('周', '') || ''} ${dayTime.value} 执行` } else if (scheduleMode.value === 'MONTHLY') { scheduleForm.cronExpression = `${Number(minute)} ${Number(hour)} ${monthDay.value} * *`; scheduleForm.scheduleConfig = { mode: 'MONTHLY', day: monthDay.value, time: dayTime.value }; scheduleForm.scheduleLabel = `每月 ${monthDay.value} 日 ${dayTime.value} 执行` } }
async function loadCronPreview() { if (scheduleForm.scheduleType !== 'CRON' || !scheduleForm.cronExpression) { cronPreview.value = []; return } const result = await previewCronExpression({ cronExpression: scheduleForm.cronExpression, timezone: scheduleForm.scheduleTimezone || 'Asia/Shanghai', count: 5 }); cronPreview.value = result.nextTimes; scheduleForm.cronExpression = result.cronExpression }
async function saveSchedule() { if (!selectedTask.value) return; if (scheduleForm.scheduleType === 'CRON') await loadCronPreview(); await ElMessageBox.confirm(`确认修改任务“${selectedTask.value.taskName}”的调度时间？\n修改后：${scheduleForm.scheduleLabel || scheduleForm.cronExpression || '手动执行'}\n重叠策略：${zh(scheduleForm.overlapPolicy || '')}`, '调度变更确认', { type: 'warning' }); await updateTaskSchedule(selectedTask.value.taskId, scheduleForm); scheduleVisible.value = false; ElMessage.success('调度已更新'); await loadAllForProject() }
onMounted(loadCompaniesAndProjects)
</script>
<style scoped>
:deep(.disabled-row) { color: #999; background: #f5f7fa; }
.schedule-form { margin-top: 16px; }
.preview-box { margin-top: 12px; padding: 12px 16px; background: #f7f8fa; border-radius: 6px; }
.preview-box ul { margin: 8px 0 0; }
</style>

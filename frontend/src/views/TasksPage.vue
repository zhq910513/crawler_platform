<template>
  <div class="page-card task-schedule-page">
    <div class="page-heading">
      <div>
        <h2>任务调度工作台</h2>
        <p>统一查看公司、项目、执行节点、调度计划与最近运行结果。</p>
      </div>
      <el-button type="primary" @click="openCreate">新增任务</el-button>
    </div>

    <el-form class="filter-card" label-position="top">
      <el-row :gutter="14">
        <el-col v-if="sessionState.user?.isSuperAdmin" :xl="4" :lg="6" :md="8" :sm="12">
          <el-form-item label="公司">
            <el-select v-model="query.companyId" clearable filterable placeholder="全部公司" @change="handleCompanyChange">
              <el-option v-for="company in companies" :key="company.companyId" :label="company.companyName" :value="company.companyId" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col v-else :xl="4" :lg="6" :md="8" :sm="12">
          <el-form-item label="公司"><el-input :model-value="currentCompanyName" disabled /></el-form-item>
        </el-col>
        <el-col :xl="4" :lg="6" :md="8" :sm="12">
          <el-form-item label="项目">
            <el-select v-model="query.projectId" clearable filterable placeholder="全部项目">
              <el-option v-for="project in filteredProjects" :key="project.projectId" :label="project.projectName" :value="project.projectId" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xl="4" :lg="6" :md="8" :sm="12"><el-form-item label="任务名称"><el-input v-model="query.taskName" clearable placeholder="模糊搜索任务名称" @keyup.enter="search" /></el-form-item></el-col>
        <el-col :xl="4" :lg="6" :md="8" :sm="12"><el-form-item label="目标任务路径"><el-input v-model="query.entryKeyword" clearable placeholder="模块或函数" @keyup.enter="search" /></el-form-item></el-col>
        <el-col :xl="4" :lg="6" :md="8" :sm="12"><el-form-item label="任务编码"><el-input v-model="query.taskCode" clearable placeholder="任务编码" @keyup.enter="search" /></el-form-item></el-col>
        <el-col :xl="4" :lg="6" :md="8" :sm="12">
          <el-form-item label="执行节点">
            <el-select v-model="query.serverId" clearable filterable placeholder="全部节点">
              <el-option v-for="server in filteredServers" :key="server.serverId" :label="serverLabel(server)" :value="server.serverId" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="14">
        <el-col :xl="4" :lg="6" :md="8" :sm="12"><el-form-item label="任务组"><el-input v-model="query.taskGroup" clearable placeholder="如 browser / api" @keyup.enter="search" /></el-form-item></el-col>
        <el-col :xl="4" :lg="6" :md="8" :sm="12"><el-form-item label="任务平台"><el-input v-model="query.taskPlatform" clearable placeholder="项目或任务组" @keyup.enter="search" /></el-form-item></el-col>
        <el-col :xl="4" :lg="6" :md="8" :sm="12">
          <el-form-item label="任务状态"><el-select v-model="query.taskStatus" clearable placeholder="全部"><el-option v-for="item in taskStatusOptions" :key="item" :label="statusText(item)" :value="item" /></el-select></el-form-item>
        </el-col>
        <el-col :xl="4" :lg="6" :md="8" :sm="12">
          <el-form-item label="调度状态"><el-select v-model="query.scheduleStatus" clearable placeholder="全部"><el-option v-for="item in scheduleStatusOptions" :key="item" :label="statusText(item)" :value="item" /></el-select></el-form-item>
        </el-col>
        <el-col :xl="4" :lg="6" :md="8" :sm="12">
          <el-form-item label="最近运行状态"><el-select v-model="query.lastRunStatus" clearable placeholder="全部"><el-option v-for="item in runStatusOptions" :key="item" :label="statusText(item)" :value="item" /></el-select></el-form-item>
        </el-col>
        <el-col v-if="sessionState.user?.isSuperAdmin" :xl="4" :lg="6" :md="8" :sm="12">
          <el-form-item label="负责人"><el-select v-model="query.ownerUserId" clearable filterable placeholder="全部负责人"><el-option v-for="user in filteredOwnerUsers" :key="user.userId" :label="user.nickName || user.userName" :value="user.userId" /></el-select></el-form-item>
        </el-col>
      </el-row>
      <div class="filter-actions">
        <el-button type="primary" :loading="loading" @click="search">搜索</el-button>
        <el-button @click="resetFilters">重置</el-button>
        <el-button :loading="loading" @click="loadPanel">刷新</el-button>
      </div>
    </el-form>

    <div class="table-toolbar">
      <div class="summary">共 <b>{{ total }}</b> 条任务</div>
      <div class="legend"><el-tag type="success">成功</el-tag><el-tag type="danger">失败</el-tag><el-tag type="primary">运行中</el-tag><el-tag type="info">未运行</el-tag></div>
    </div>

    <el-table v-loading="loading" :data="rows" border stripe row-key="taskId" class="panel-table">
      <el-table-column label="任务ID" prop="taskId" width="86" fixed="left" />
      <el-table-column v-if="sessionState.user?.isSuperAdmin" label="公司" prop="companyName" min-width="130" show-overflow-tooltip />
      <el-table-column label="项目" prop="projectName" min-width="150" show-overflow-tooltip />
      <el-table-column label="执行节点" min-width="170">
        <template #default="s">
          <div>{{ s.row.serverName || '-' }}</div>
          <div v-if="s.row.serverIp" class="cell-subtitle">{{ s.row.serverIp }}</div>
        </template>
      </el-table-column>
      <el-table-column label="任务平台" prop="taskPlatform" min-width="110" show-overflow-tooltip />
      <el-table-column label="任务名称" prop="taskName" min-width="190" show-overflow-tooltip />
      <el-table-column label="目标任务路径" prop="entryPath" min-width="260" show-overflow-tooltip />
      <el-table-column label="任务编码" prop="taskCode" min-width="170" show-overflow-tooltip />
      <el-table-column label="Cron / 调度" min-width="190" show-overflow-tooltip>
        <template #default="s"><span>{{ scheduleText(s.row) }}</span></template>
      </el-table-column>
      <el-table-column label="下次执行时间" min-width="168"><template #default="s">{{ formatTime(s.row.nextRunAt) }}</template></el-table-column>
      <el-table-column label="最近完成时间" min-width="168"><template #default="s">{{ formatTime(s.row.lastFinishedAt) }}</template></el-table-column>
      <el-table-column label="负责人" min-width="110"><template #default="s">{{ s.row.ownerUserName || '-' }}</template></el-table-column>
      <el-table-column label="任务状态" width="105"><template #default="s"><el-tag :type="taskTagType(s.row.taskStatus)">{{ statusText(s.row.taskStatus) }}</el-tag></template></el-table-column>
      <el-table-column label="自动调度" width="100" align="center">
        <template #default="s">
          <el-tooltip :content="s.row.scheduleType === 'CRON' ? statusText(s.row.scheduleStatus) : '手动任务无自动调度'">
            <el-switch :model-value="s.row.scheduleStatus === 'ENABLED'" :disabled="s.row.scheduleType !== 'CRON'" @change="toggleSchedule(s.row, Boolean($event))" />
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="最近结果" width="115"><template #default="s"><el-tag :type="runTagType(s.row.lastRunStatus)">{{ statusText(s.row.lastRunStatus) }}</el-tag></template></el-table-column>
      <el-table-column label="操作" width="310" fixed="right">
        <template #default="s">
          <el-button link type="primary" @click="manualRun(s.row)">立即执行</el-button>
          <el-button link @click="openEdit(s.row)">编辑</el-button>
          <el-button link @click="openSchedule(s.row)">调度</el-button>
          <el-button link @click="openDetail(s.row)">详情</el-button>
          <el-button link :disabled="!s.row.lastRunId" @click="openLogs(s.row)">日志</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-wrap">
      <el-pagination v-model:current-page="query.page" v-model:page-size="query.pageSize" :page-sizes="[20, 50, 100, 200]" :total="total" layout="total, sizes, prev, pager, next, jumper" @current-change="loadPanel" @size-change="handlePageSizeChange" />
    </div>

    <el-dialog v-model="createVisible" title="新增正式任务" width="840px" destroy-on-close>
      <el-form label-position="top">
        <el-row :gutter="16">
          <el-col :span="12" v-if="sessionState.user?.isSuperAdmin"><el-form-item label="所属公司" required><el-select v-model="createContext.companyId" filterable @change="loadCreateProjects"><el-option v-for="company in companies" :key="company.companyId" :label="company.companyName" :value="company.companyId" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="所属项目" required><el-select v-model="createContext.projectId" filterable @change="loadCreateResources"><el-option v-for="project in createProjects" :key="project.projectId" :label="`${project.projectName}（${project.projectCode}）`" :value="project.projectId" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="任务目录" required><el-select v-model="createForm.definitionId" filterable @change="applyDefinition"><el-option v-for="definition in definitions" :key="definition.definitionId" :label="`${definition.taskName}（${definition.definitionKey}）`" :value="definition.definitionId" :disabled="definition.definitionStatus !== 'AVAILABLE'" /></el-select></el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="任务编码" required><el-input v-model="createForm.taskCode" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="任务名称" required><el-input v-model="createForm.taskName" /></el-form-item></el-col>
          <el-col v-if="sessionState.user?.isSuperAdmin" :span="12"><el-form-item label="负责人"><el-select v-model="createForm.ownerUserId" clearable filterable><el-option v-for="user in createOwnerUsers" :key="user.userId" :label="user.nickName || user.userName" :value="user.userId" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="任务状态"><el-select v-model="createForm.status"><el-option label="启用" value="ENABLED" /><el-option label="草稿" value="DRAFT" /><el-option label="暂停" value="PAUSED" /></el-select></el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8"><el-form-item label="调度类型"><el-select v-model="createForm.scheduleType"><el-option label="手动" value="MANUAL" /><el-option label="Cron 定时" value="CRON" /></el-select></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="调度状态"><el-select v-model="createForm.scheduleStatus"><el-option label="启用" value="ENABLED" /><el-option label="暂停" value="PAUSED" /><el-option label="停用" value="DISABLED" /></el-select></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="任务组"><el-input v-model="createForm.taskGroup" /></el-form-item></el-col>
        </el-row>
        <el-form-item v-if="createForm.scheduleType === 'CRON'" label="Cron 表达式"><el-input v-model="createForm.cronExpression" placeholder="5 段格式：分钟 小时 日 月 星期" /></el-form-item>
        <el-form-item label="指定服务器"><el-select v-model="createForm.serverIds" multiple clearable filterable placeholder="为空时使用项目服务器池"><el-option v-for="server in createProjectServers" :key="server.serverId" :label="server.serverName || String(server.serverId)" :value="server.serverId" /></el-select></el-form-item>
        <el-collapse>
          <el-collapse-item title="高级执行配置" name="advanced">
            <el-row :gutter="16">
              <el-col :span="8"><el-form-item label="运行模式"><el-select v-model="createForm.runtimeMode"><el-option label="共享环境隔离容器" value="SHARED_ENV_ISOLATED" /><el-option label="常驻 Worker 池" value="WORKER_POOL" /><el-option label="独占容器" value="DEDICATED_CONTAINER" /></el-select></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="任务最大并发"><el-input-number v-model="createForm.taskMaxConcurrency" :min="1" :max="1000" /></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="任务组最大并发"><el-input-number v-model="createForm.groupMaxConcurrency" :min="1" :max="1000" /></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="共享内存 MB"><el-input-number v-model="createForm.shmSizeMb" :min="16" :max="65536" /></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="日志上限 MB"><el-input-number v-model="createForm.logLimitMb" :min="1" :max="10240" /></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="独占运行"><el-switch v-model="createForm.exclusiveMode" /></el-form-item></el-col>
            </el-row>
            <el-form-item label="资源锁"><el-input v-model="createLocksText" placeholder="多个资源锁用英文逗号分隔" /></el-form-item>
            <el-form-item label="任务参数 JSON"><el-input v-model="createParamsText" type="textarea" :rows="5" /></el-form-item>
          </el-collapse-item>
        </el-collapse>
      </el-form>
      <template #footer><el-button @click="createVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveTask">保存任务</el-button></template>
    </el-dialog>

    <el-drawer v-model="editVisible" title="编辑任务" size="560px">
      <el-form label-position="top">
        <el-form-item label="任务名称"><el-input v-model="editForm.taskName" /></el-form-item>
        <el-form-item v-if="sessionState.user?.isSuperAdmin" label="负责人"><el-select v-model="editForm.ownerUserId" clearable filterable><el-option v-for="user in editOwnerUsers" :key="user.userId" :label="user.nickName || user.userName" :value="user.userId" /></el-select></el-form-item>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="任务状态"><el-select v-model="editForm.status"><el-option v-for="item in taskStatusOptions" :key="item" :label="statusText(item)" :value="item" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="任务组"><el-input v-model="editForm.taskGroup" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="超时时间（秒）"><el-input-number v-model="editForm.timeoutSeconds" :min="1" :max="604800" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="最大重试次数"><el-input-number v-model="editForm.maxRetryCount" :min="0" :max="20" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="描述"><el-input v-model="editForm.description" type="textarea" :rows="4" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="editVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button></template>
    </el-drawer>

    <el-dialog v-model="scheduleVisible" title="修改任务调度" width="860px">
      <el-alert title="平台使用 5 段 Cron：分钟 小时 日 月 星期，并兼容每日、每周、每月多时间点配置。" type="info" show-icon :closable="false" />
      <el-form label-position="top" class="schedule-form">
        <el-row :gutter="16">
          <el-col :span="8"><el-form-item label="调度状态"><el-select v-model="scheduleForm.scheduleStatus"><el-option label="启用" value="ENABLED" /><el-option label="暂停" value="PAUSED" /><el-option label="停用" value="DISABLED" /></el-select></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="调度类型"><el-select v-model="scheduleForm.scheduleType"><el-option label="手动" value="MANUAL" /><el-option label="定时" value="CRON" /></el-select></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="重叠策略"><el-select v-model="scheduleForm.overlapPolicy"><el-option label="排队等待" value="QUEUE" /><el-option label="跳过新触发" value="SKIP" /><el-option label="允许并发" value="CONCURRENT" /><el-option label="取消旧任务" value="CANCEL_OLD" /></el-select></el-form-item></el-col>
        </el-row>
        <template v-if="scheduleForm.scheduleType === 'CRON'">
          <el-form-item label="快捷设置">
            <el-radio-group v-model="scheduleMode" @change="applyScheduleMode">
              <el-radio-button label="EVERY_N_MINUTES">每 N 分钟</el-radio-button><el-radio-button label="EVERY_N_HOURS">每 N 小时</el-radio-button><el-radio-button label="DAILY">每天</el-radio-button><el-radio-button label="DAILY_TIMES">每天多时间点</el-radio-button><el-radio-button label="WEEKLY">每周</el-radio-button><el-radio-button label="WEEKLY_TIMES">每周多日期/时间</el-radio-button><el-radio-button label="MONTHLY">每月</el-radio-button><el-radio-button label="MONTHLY_TIMES">每月多日期/时间</el-radio-button><el-radio-button label="ADVANCED">高级 Cron</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-row v-if="scheduleMode === 'EVERY_N_MINUTES'" :gutter="16"><el-col :span="8"><el-form-item label="间隔分钟"><el-input-number v-model="intervalMinutes" :min="5" :max="59" @change="applyScheduleMode" /></el-form-item></el-col></el-row>
          <el-row v-if="scheduleMode === 'EVERY_N_HOURS'" :gutter="16"><el-col :span="8"><el-form-item label="间隔小时"><el-input-number v-model="intervalHours" :min="1" :max="24" @change="applyScheduleMode" /></el-form-item></el-col></el-row>
          <el-row v-if="['DAILY','WEEKLY','MONTHLY'].includes(scheduleMode)" :gutter="16">
            <el-col v-if="scheduleMode === 'WEEKLY'" :span="8"><el-form-item label="星期"><el-select v-model="weekday" @change="applyScheduleMode"><el-option v-for="day in weekdayOptions" :key="day.value" :label="day.label" :value="day.value" /></el-select></el-form-item></el-col>
            <el-col v-if="scheduleMode === 'MONTHLY'" :span="8"><el-form-item label="日期"><el-input-number v-model="monthDay" :min="1" :max="31" @change="applyScheduleMode" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="时间"><el-time-picker v-model="dayTime" format="HH:mm" value-format="HH:mm" @change="applyScheduleMode" /></el-form-item></el-col>
          </el-row>
          <div v-if="['DAILY_TIMES','WEEKLY_TIMES','MONTHLY_TIMES'].includes(scheduleMode)" class="daily-times-box">
            <el-form-item v-if="scheduleMode === 'WEEKLY_TIMES'" label="每周执行日期"><el-select v-model="weeklyDays" multiple clearable @change="applyScheduleMode"><el-option v-for="day in weekdayOptions" :key="day.value" :label="day.label" :value="day.value" /></el-select></el-form-item>
            <el-form-item v-if="scheduleMode === 'MONTHLY_TIMES'" label="每月执行日期"><el-select v-model="monthlyDays" multiple clearable @change="applyScheduleMode"><el-option v-for="day in monthlyDayOptions" :key="day" :label="`${day} 日`" :value="day" /></el-select></el-form-item>
            <el-form-item label="执行时间点"><div class="time-tags"><el-tag v-for="item in dailyTimes" :key="item" closable @close="removeDailyTime(item)">{{ item }}</el-tag></div></el-form-item>
            <el-row :gutter="16"><el-col :span="8"><el-form-item label="新增时间"><el-time-picker v-model="newDailyTime" format="HH:mm" value-format="HH:mm" /></el-form-item></el-col><el-col :span="8"><el-form-item label=" "><el-button @click="addDailyTime">添加时间点</el-button></el-form-item></el-col></el-row>
          </div>
          <el-form-item label="Cron 表达式"><el-input v-model="scheduleForm.cronExpression" @input="scheduleMode = 'ADVANCED'" /></el-form-item>
          <el-form-item label="时区"><el-input v-model="scheduleForm.scheduleTimezone" /></el-form-item>
          <el-button @click="loadCronPreview">校验并预览最近 5 次</el-button>
          <div class="preview-box"><div class="cell-subtitle">最近 5 次预计执行时间</div><ul><li v-for="item in cronPreview" :key="item">{{ item }}</li></ul></div>
        </template>
      </el-form>
      <template #footer><el-button @click="scheduleVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveSchedule">保存调度</el-button></template>
    </el-dialog>

    <el-drawer v-model="detailVisible" title="任务调度详情" size="620px">
      <el-descriptions v-if="detailRow" :column="1" border>
        <el-descriptions-item label="公司 / 项目">{{ detailRow.companyName }} / {{ detailRow.projectName }}</el-descriptions-item>
        <el-descriptions-item label="任务">{{ detailRow.taskName }}（{{ detailRow.taskCode }}）</el-descriptions-item>
        <el-descriptions-item label="入口路径">{{ detailRow.entryPath }}</el-descriptions-item>
        <el-descriptions-item label="执行节点">{{ detailRow.serverName || '-' }} {{ detailRow.serverIp || '' }}</el-descriptions-item>
        <el-descriptions-item label="负责人">{{ detailRow.ownerUserName || '-' }}</el-descriptions-item>
        <el-descriptions-item label="调度">{{ scheduleText(detailRow) }}</el-descriptions-item>
        <el-descriptions-item label="时区">{{ detailRow.scheduleTimezone || '-' }}</el-descriptions-item>
        <el-descriptions-item label="下次执行">{{ formatTime(detailRow.nextRunAt) }}</el-descriptions-item>
        <el-descriptions-item label="最近结果">{{ statusText(detailRow.lastRunStatus) }}</el-descriptions-item>
        <el-descriptions-item label="路由状态">{{ statusText(detailRow.routingStatus) }}</el-descriptions-item>
        <el-descriptions-item label="最近完成">{{ formatTime(detailRow.lastFinishedAt) }}</el-descriptions-item>
        <el-descriptions-item label="最近错误">{{ detailRow.lastErrorSummary || '-' }}</el-descriptions-item>
      </el-descriptions>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { createRun, createTask, listCompanies, listProjectServers, listProjects, listServers, listTaskDefinitions, listTasks, listUsers, previewCronExpression, updateTask, updateTaskSchedule } from '../api/platform'
import { listTaskSchedulePanels } from '../api/taskSchedules'
import { sessionState } from '../stores/session'
import type { Company, Project, ProjectServer, ScheduleUpdateRequest, ServerNode, Task, TaskCreateRequest, TaskDefinition, TaskSchedulePanelItem, TaskUpdateRequest, UserAccount } from '../types/api'
import { formatTime } from '../utils/dictionaries'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const rows = ref<TaskSchedulePanelItem[]>([])
const total = ref(0)
const companies = ref<Company[]>([])
const projects = ref<Project[]>([])
const servers = ref<ServerNode[]>([])
const ownerUsers = ref<UserAccount[]>([])
const query = reactive({ companyId: undefined as number | undefined, projectId: undefined as number | undefined, taskName: '', taskCode: '', entryKeyword: '', serverId: undefined as number | undefined, taskGroup: '', taskPlatform: '', taskStatus: '', scheduleStatus: '', lastRunStatus: '', ownerUserId: undefined as number | undefined, page: 1, pageSize: 20 })
const taskStatusOptions = ['ENABLED', 'DRAFT', 'PAUSED', 'DISABLED', 'ARCHIVED']
const scheduleStatusOptions = ['ENABLED', 'PAUSED', 'DISABLED', 'ERROR', 'NONE']
const runStatusOptions = ['QUEUED', 'ROUTED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELED', 'CANCELLED', 'TIMED_OUT', 'TIMEOUT', 'LOST', 'NOT_RUN']
const currentCompanyName = computed(() => companies.value.find((item) => item.companyId === sessionState.user?.companyId)?.companyName || '归属公司')
const effectiveCompanyId = computed(() => sessionState.user?.isSuperAdmin ? query.companyId : sessionState.user?.companyId || undefined)
const filteredProjects = computed(() => effectiveCompanyId.value ? projects.value.filter((item) => item.companyId === effectiveCompanyId.value) : projects.value)
const filteredServers = computed(() => effectiveCompanyId.value ? servers.value.filter((item) => item.companyId === effectiveCompanyId.value) : servers.value)
const filteredOwnerUsers = computed(() => effectiveCompanyId.value ? ownerUsers.value.filter((item) => item.companyId === effectiveCompanyId.value && item.status === 'ENABLED') : ownerUsers.value.filter((item) => item.status === 'ENABLED'))

const createVisible = ref(false)
const createContext = reactive({ companyId: undefined as number | undefined, projectId: undefined as number | undefined })
const createProjects = ref<Project[]>([])
const definitions = ref<TaskDefinition[]>([])
const createProjectServers = ref<ProjectServer[]>([])
const createParamsText = ref('{}')
const createLocksText = ref('')
const createForm = reactive<TaskCreateRequest>({ definitionId: 0, ownerUserId: null, taskCode: '', taskName: '', parameters: {}, status: 'ENABLED', imagePolicy: 'RELEASE_CHANNEL', releaseChannel: 'stable', scheduleStatus: 'PAUSED', scheduleType: 'MANUAL', cronExpression: '', scheduleTimezone: 'Asia/Shanghai', overlapPolicy: 'QUEUE', scheduleConfig: {}, scheduleLabel: '', serverIds: [], runtimeMode: 'SHARED_ENV_ISOLATED', taskGroup: 'default', taskMaxConcurrency: 1, groupMaxConcurrency: 4, exclusiveMode: false, ioClass: 'NORMAL', shmSizeMb: 64, logLimitMb: 50, resourceLocks: [] })
const createOwnerUsers = computed(() => ownerUsers.value.filter((item) => item.companyId === createContext.companyId && item.status === 'ENABLED'))

const editVisible = ref(false)
const editTask = ref<Task | null>(null)
const editForm = reactive<TaskUpdateRequest>({ ownerUserId: null, taskName: '', status: 'ENABLED', taskGroup: 'default', timeoutSeconds: 3600, maxRetryCount: 0, description: '' })
const editOwnerUsers = computed(() => ownerUsers.value.filter((item) => item.companyId === editTask.value?.companyId && item.status === 'ENABLED'))

const scheduleVisible = ref(false)
const selectedScheduleRow = ref<TaskSchedulePanelItem | null>(null)
const scheduleForm = reactive<ScheduleUpdateRequest>({ scheduleStatus: 'PAUSED', scheduleType: 'MANUAL', cronExpression: '', scheduleTimezone: 'Asia/Shanghai', overlapPolicy: 'QUEUE', scheduleConfig: {}, scheduleLabel: '' })
const scheduleMode = ref('DAILY')
const intervalMinutes = ref(30)
const intervalHours = ref(1)
const weekday = ref(1)
const weeklyDays = ref<number[]>([1, 3, 5])
const monthDay = ref(1)
const monthlyDays = ref<number[]>([1, 15])
const dayTime = ref('08:00')
const dailyTimes = ref<string[]>(['07:00', '09:00', '12:00'])
const newDailyTime = ref('08:00')
const cronPreview = ref<string[]>([])
const weekdayOptions = [{ label: '周一', value: 1 }, { label: '周二', value: 2 }, { label: '周三', value: 3 }, { label: '周四', value: 4 }, { label: '周五', value: 5 }, { label: '周六', value: 6 }, { label: '周日', value: 0 }]
const monthlyDayOptions = Array.from({ length: 31 }, (_, index) => index + 1)

const detailVisible = ref(false)
const detailRow = ref<TaskSchedulePanelItem | null>(null)

function serverLabel(server: ServerNode) { return `${server.serverName}${server.serverIp ? `（${server.serverIp}）` : ''}` }
function statusText(value?: string | null) {
  const map: Record<string, string> = { ENABLED: '启用', DISABLED: '停用', PAUSED: '暂停', DRAFT: '草稿', ARCHIVED: '归档', ERROR: '异常', NONE: '无调度', QUEUED: '排队中', ROUTED: '已路由', RUNNING: '运行中', STARTING: '启动中', ASSIGNED: '已分配', SUCCEEDED: '成功', FAILED: '失败', CANCELED: '已取消', CANCELLED: '已取消', TIMED_OUT: '超时', TIMEOUT: '超时', LOST: '失联', NOT_RUN: '未运行', WAITING_RESOURCE: '等待资源', NO_AVAILABLE_SERVER: '无可用节点', PENDING: '待处理' }
  return value ? (map[value] || value) : '-'
}
type TagType = '' | 'primary' | 'success' | 'warning' | 'info' | 'danger'
function taskTagType(status: string): TagType { if (status === 'ENABLED') return 'success'; if (status === 'DISABLED' || status === 'ARCHIVED') return 'info'; if (status === 'PAUSED') return 'warning'; return '' }
function runTagType(status: string): TagType { if (status === 'SUCCEEDED') return 'success'; if (['FAILED', 'TIMED_OUT', 'TIMEOUT', 'LOST', 'CANCELED', 'CANCELLED'].includes(status)) return 'danger'; if (['RUNNING', 'STARTING', 'ASSIGNED', 'ROUTED'].includes(status)) return 'primary'; if (['QUEUED', 'WAITING_RESOURCE'].includes(status)) return 'warning'; return 'info' }
function scheduleText(row: TaskSchedulePanelItem) { if (row.scheduleType !== 'CRON') return '手动执行'; return row.scheduleLabel || row.cronExpression || '-' }

async function loadOptions() {
  const [companyRows, projectRows, serverRows] = await Promise.all([listCompanies(), listProjects(), listServers()])
  companies.value = companyRows
  projects.value = projectRows
  servers.value = serverRows
  if (!sessionState.user?.isSuperAdmin) query.companyId = sessionState.user?.companyId || undefined
  if (sessionState.user?.isSuperAdmin) ownerUsers.value = await listUsers()
}
async function loadPanel() {
  loading.value = true
  try {
    const result = await listTaskSchedulePanels({ ...query, companyId: effectiveCompanyId.value, taskName: query.taskName || undefined, taskCode: query.taskCode || undefined, entryKeyword: query.entryKeyword || undefined, taskGroup: query.taskGroup || undefined, taskPlatform: query.taskPlatform || undefined, taskStatus: query.taskStatus || undefined, scheduleStatus: query.scheduleStatus || undefined, lastRunStatus: query.lastRunStatus || undefined })
    rows.value = result.items
    total.value = result.total
    query.page = result.page
    query.pageSize = result.pageSize
  } finally { loading.value = false }
}
async function search() { query.page = 1; await loadPanel() }
async function handleCompanyChange() {
  query.projectId = undefined
  query.serverId = undefined
  query.ownerUserId = undefined
  await loadPanel()
}
async function resetFilters() {
  Object.assign(query, { companyId: sessionState.user?.isSuperAdmin ? undefined : sessionState.user?.companyId || undefined, projectId: undefined, taskName: '', taskCode: '', entryKeyword: '', serverId: undefined, taskGroup: '', taskPlatform: '', taskStatus: '', scheduleStatus: '', lastRunStatus: '', ownerUserId: undefined, page: 1, pageSize: 20 })
  await loadPanel()
}
async function handlePageSizeChange() { query.page = 1; await loadPanel() }

function resetCreateForm() {
  Object.assign(createForm, { definitionId: 0, ownerUserId: sessionState.user?.isSuperAdmin ? null : sessionState.user?.userId || null, taskCode: '', taskName: '', parameters: {}, status: 'ENABLED', imagePolicy: 'RELEASE_CHANNEL', releaseChannel: 'stable', scheduleStatus: 'PAUSED', scheduleType: 'MANUAL', cronExpression: '', scheduleTimezone: 'Asia/Shanghai', overlapPolicy: 'QUEUE', scheduleConfig: {}, scheduleLabel: '', serverIds: [], runtimeMode: 'SHARED_ENV_ISOLATED', taskGroup: 'default', taskMaxConcurrency: 1, groupMaxConcurrency: 4, exclusiveMode: false, ioClass: 'NORMAL', shmSizeMb: 64, logLimitMb: 50, resourceLocks: [] })
  createParamsText.value = '{}'
  createLocksText.value = ''
}
async function openCreate() {
  resetCreateForm()
  createContext.companyId = sessionState.user?.isSuperAdmin ? (query.companyId || companies.value[0]?.companyId) : sessionState.user?.companyId || undefined
  createVisible.value = true
  await loadCreateProjects()
}
async function loadCreateProjects() {
  const all = await listProjects(createContext.companyId)
  createProjects.value = createContext.companyId ? all.filter((item) => item.companyId === createContext.companyId) : all
  createContext.projectId = createProjects.value[0]?.projectId
  await loadCreateResources()
}
async function loadCreateResources() {
  definitions.value = []
  createProjectServers.value = []
  createForm.definitionId = 0
  if (!createContext.projectId) return
  const [definitionRows, serverRows] = await Promise.all([listTaskDefinitions(createContext.projectId), listProjectServers(createContext.projectId)])
  definitions.value = definitionRows
  createProjectServers.value = serverRows.filter((item) => item.deploymentStatus === 'DEPLOYED' && item.schedulingStatus !== 'DISABLED')
  const available = definitions.value.find((item) => item.definitionStatus === 'AVAILABLE')
  if (available) { createForm.definitionId = available.definitionId; applyDefinition() }
}
function applyDefinition() {
  const row = definitions.value.find((item) => item.definitionId === createForm.definitionId)
  if (!row) return
  createForm.taskCode = row.definitionKey
  createForm.taskName = row.taskName
  createForm.cronExpression = row.suggestedCron || ''
  createForm.scheduleType = row.suggestedCron ? 'CRON' : 'MANUAL'
  createForm.scheduleStatus = 'PAUSED'
  createForm.runtimeMode = row.runtimeMode || 'SHARED_ENV_ISOLATED'
  createForm.taskGroup = row.taskGroup || 'default'
  createForm.taskMaxConcurrency = row.taskMaxConcurrency || 1
  createForm.groupMaxConcurrency = row.groupMaxConcurrency || 4
  createForm.exclusiveMode = row.exclusiveMode || false
  createForm.ioClass = row.ioClass || 'NORMAL'
  createForm.shmSizeMb = row.shmSizeMb || 64
  createForm.logLimitMb = row.logLimitMb || 50
  createParamsText.value = JSON.stringify(row.defaultParams || {}, null, 2)
  createLocksText.value = (row.resourceLocks || []).join(',')
}
async function saveTask() {
  if (!createContext.projectId || !createForm.definitionId) { ElMessage.warning('请选择项目和可创建的任务目录'); return }
  let parameters: Record<string, unknown>
  try { parameters = JSON.parse(createParamsText.value || '{}') } catch { ElMessage.error('任务参数不是合法 JSON'); return }
  saving.value = true
  try {
    createForm.parameters = parameters
    createForm.resourceLocks = createLocksText.value.split(',').map((item) => item.trim()).filter(Boolean)
    await createTask(createForm)
    createVisible.value = false
    ElMessage.success('正式任务已创建')
    await loadPanel()
  } finally { saving.value = false }
}

async function openEdit(row: TaskSchedulePanelItem) {
  const taskRows = await listTasks({ projectId: row.projectId })
  const task = taskRows.find((item) => item.taskId === row.taskId)
  if (!task) { ElMessage.error('未找到任务详情'); return }
  editTask.value = task
  Object.assign(editForm, { ownerUserId: task.ownerUserId ?? null, taskName: task.taskName, status: task.status, taskGroup: task.taskGroup || 'default', timeoutSeconds: task.timeoutSeconds, maxRetryCount: task.maxRetryCount, description: task.description || '' })
  editVisible.value = true
}
async function saveEdit() {
  if (!editTask.value) return
  saving.value = true
  try { await updateTask(editTask.value.taskId, editForm); editVisible.value = false; ElMessage.success('任务已更新'); await loadPanel() } finally { saving.value = false }
}
async function manualRun(row: TaskSchedulePanelItem) {
  await ElMessageBox.confirm(`确认立即执行任务“${row.taskName}”？`, '立即执行确认', { type: 'warning' })
  const run = await createRun(row.taskId)
  ElMessage.success(`已创建运行实例 #${run.runId}`)
  await loadPanel()
}
async function toggleSchedule(row: TaskSchedulePanelItem, enabled: boolean) {
  const message = enabled ? '确认启用该任务自动调度？' : '确认停用后该任务不会自动运行，但仍可手动执行。'
  try {
    await ElMessageBox.confirm(message, enabled ? '启用调度' : '停用调度', { type: 'warning' })
    await updateTaskSchedule(row.taskId, { scheduleStatus: enabled ? 'ENABLED' : 'DISABLED' })
    ElMessage.success(enabled ? '调度已启用' : '调度已停用')
    await loadPanel()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') throw error
  }
}
function openDetail(row: TaskSchedulePanelItem) { detailRow.value = row; detailVisible.value = true }
async function openLogs(row: TaskSchedulePanelItem) { if (!row.lastRunId) return; await router.push({ path: '/runs', query: { taskId: String(row.taskId), runId: String(row.lastRunId) } }) }

function openSchedule(row: TaskSchedulePanelItem) {
  selectedScheduleRow.value = row
  scheduleForm.scheduleStatus = row.scheduleStatus === 'NONE' ? 'PAUSED' : row.scheduleStatus
  scheduleForm.scheduleType = row.scheduleType || 'MANUAL'
  scheduleForm.cronExpression = row.cronExpression || '0 8 * * *'
  scheduleForm.scheduleTimezone = row.scheduleTimezone || 'Asia/Shanghai'
  scheduleForm.overlapPolicy = row.overlapPolicy || 'QUEUE'
  scheduleForm.scheduleConfig = row.scheduleConfig || {}
  scheduleForm.scheduleLabel = row.scheduleLabel || ''
  const mode = String(scheduleForm.scheduleConfig?.mode || '')
  if (mode === 'daily_times') { scheduleMode.value = 'DAILY_TIMES'; dailyTimes.value = normalizeDailyTimes(scheduleForm.scheduleConfig?.times as string[] | undefined) }
  else if (mode === 'weekly_times') { scheduleMode.value = 'WEEKLY_TIMES'; dailyTimes.value = normalizeDailyTimes(scheduleForm.scheduleConfig?.times as string[] | undefined); weeklyDays.value = ((scheduleForm.scheduleConfig?.weekdays as number[] | undefined) || [1]).map(Number) }
  else if (mode === 'monthly_times') { scheduleMode.value = 'MONTHLY_TIMES'; dailyTimes.value = normalizeDailyTimes(scheduleForm.scheduleConfig?.times as string[] | undefined); monthlyDays.value = ((scheduleForm.scheduleConfig?.days as number[] | undefined) || [1]).map(Number) }
  else scheduleMode.value = mode ? mode.toUpperCase() : 'ADVANCED'
  cronPreview.value = []
  scheduleVisible.value = true
  if (scheduleForm.scheduleType === 'CRON') void loadCronPreview()
}
function normalizeDailyTimes(values?: string[]) { const pattern = /^([01]\d|2[0-3]):[0-5]\d$/; return Array.from(new Set((values || []).filter((item) => pattern.test(item)))).sort() }
function addDailyTime() { dailyTimes.value = normalizeDailyTimes([...dailyTimes.value, newDailyTime.value]); applyScheduleMode() }
function removeDailyTime(value: string) { dailyTimes.value = dailyTimes.value.filter((item) => item !== value); applyScheduleMode() }
function applyScheduleMode() {
  const [hour, minute] = dayTime.value.split(':')
  if (scheduleMode.value === 'EVERY_N_MINUTES') { scheduleForm.cronExpression = `*/${intervalMinutes.value} * * * *`; scheduleForm.scheduleConfig = { mode: 'EVERY_N_MINUTES', intervalMinutes: intervalMinutes.value }; scheduleForm.scheduleLabel = `每 ${intervalMinutes.value} 分钟执行一次` }
  else if (scheduleMode.value === 'EVERY_N_HOURS') { scheduleForm.cronExpression = `0 */${intervalHours.value} * * *`; scheduleForm.scheduleConfig = { mode: 'EVERY_N_HOURS', intervalHours: intervalHours.value }; scheduleForm.scheduleLabel = `每 ${intervalHours.value} 小时执行一次` }
  else if (scheduleMode.value === 'DAILY') { scheduleForm.cronExpression = `${Number(minute)} ${Number(hour)} * * *`; scheduleForm.scheduleConfig = { mode: 'DAILY', time: dayTime.value }; scheduleForm.scheduleLabel = `每天 ${dayTime.value} 执行` }
  else if (scheduleMode.value === 'DAILY_TIMES') { dailyTimes.value = normalizeDailyTimes(dailyTimes.value); scheduleForm.cronExpression = ''; scheduleForm.scheduleConfig = { mode: 'daily_times', times: dailyTimes.value, timezone: scheduleForm.scheduleTimezone || 'Asia/Shanghai' }; scheduleForm.scheduleLabel = `每天 ${dailyTimes.value.join('、')} 执行` }
  else if (scheduleMode.value === 'WEEKLY_TIMES') { dailyTimes.value = normalizeDailyTimes(dailyTimes.value); weeklyDays.value = Array.from(new Set(weeklyDays.value.map(Number))).sort((a, b) => a - b); scheduleForm.cronExpression = ''; scheduleForm.scheduleConfig = { mode: 'weekly_times', weekdays: weeklyDays.value, times: dailyTimes.value, timezone: scheduleForm.scheduleTimezone || 'Asia/Shanghai' }; scheduleForm.scheduleLabel = `每周 ${weeklyDays.value.join('、')} 的 ${dailyTimes.value.join('、')} 执行` }
  else if (scheduleMode.value === 'MONTHLY_TIMES') { dailyTimes.value = normalizeDailyTimes(dailyTimes.value); monthlyDays.value = Array.from(new Set(monthlyDays.value.map(Number))).sort((a, b) => a - b); scheduleForm.cronExpression = ''; scheduleForm.scheduleConfig = { mode: 'monthly_times', days: monthlyDays.value, times: dailyTimes.value, timezone: scheduleForm.scheduleTimezone || 'Asia/Shanghai' }; scheduleForm.scheduleLabel = `每月 ${monthlyDays.value.join('、')} 日 ${dailyTimes.value.join('、')} 执行` }
  else if (scheduleMode.value === 'WEEKLY') { scheduleForm.cronExpression = `${Number(minute)} ${Number(hour)} * * ${weekday.value}`; scheduleForm.scheduleConfig = { mode: 'WEEKLY', weekday: weekday.value, time: dayTime.value }; scheduleForm.scheduleLabel = `${weekdayOptions.find((item) => item.value === weekday.value)?.label || '每周'} ${dayTime.value} 执行` }
  else if (scheduleMode.value === 'MONTHLY') { scheduleForm.cronExpression = `${Number(minute)} ${Number(hour)} ${monthDay.value} * *`; scheduleForm.scheduleConfig = { mode: 'MONTHLY', day: monthDay.value, time: dayTime.value }; scheduleForm.scheduleLabel = `每月 ${monthDay.value} 日 ${dayTime.value} 执行` }
}
async function loadCronPreview() {
  if (scheduleForm.scheduleType !== 'CRON') { cronPreview.value = []; return }
  if (['DAILY_TIMES', 'WEEKLY_TIMES', 'MONTHLY_TIMES'].includes(scheduleMode.value)) applyScheduleMode()
  const mode = String(scheduleForm.scheduleConfig?.mode || '')
  if (!scheduleForm.cronExpression && !['daily_times', 'weekly_times', 'monthly_times'].includes(mode)) { cronPreview.value = []; return }
  const result = await previewCronExpression({ cronExpression: scheduleForm.cronExpression || undefined, scheduleConfig: scheduleForm.scheduleConfig, timezone: scheduleForm.scheduleTimezone || 'Asia/Shanghai', count: 5 })
  cronPreview.value = result.nextTimes
  scheduleForm.cronExpression = result.cronExpression
  scheduleForm.scheduleConfig = result.scheduleConfig || scheduleForm.scheduleConfig
  scheduleForm.scheduleLabel = result.scheduleLabel || scheduleForm.scheduleLabel
}
async function saveSchedule() {
  if (!selectedScheduleRow.value) return
  if (scheduleForm.scheduleType === 'CRON') await loadCronPreview()
  await ElMessageBox.confirm(`确认修改任务“${selectedScheduleRow.value.taskName}”的调度？\n修改后：${scheduleForm.scheduleLabel || scheduleForm.cronExpression || '手动执行'}`, '调度变更确认', { type: 'warning' })
  saving.value = true
  try { await updateTaskSchedule(selectedScheduleRow.value.taskId, scheduleForm); scheduleVisible.value = false; ElMessage.success('调度已更新'); await loadPanel() } finally { saving.value = false }
}

onMounted(async () => { await loadOptions(); await loadPanel() })
</script>

<style scoped>
.task-schedule-page { min-width: 0; }
.page-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 18px; }
.page-heading h2 { margin: 0; font-size: 22px; color: #111827; }
.page-heading p { margin: 7px 0 0; color: #6b7280; }
.filter-card { padding: 16px 18px 8px; margin-bottom: 16px; border: 1px solid #e5e7eb; border-radius: 8px; background: #f8fafc; }
.filter-card :deep(.el-select), .filter-card :deep(.el-input) { width: 100%; }
.filter-actions { display: flex; gap: 10px; justify-content: flex-end; padding: 2px 0 8px; }
.table-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.summary { color: #4b5563; }
.legend { display: flex; gap: 6px; }
.panel-table { width: 100%; }
.cell-subtitle { margin-top: 3px; color: #8a94a6; font-size: 12px; }
.pagination-wrap { display: flex; justify-content: flex-end; margin-top: 16px; }
.schedule-form { margin-top: 16px; }
.preview-box { margin-top: 12px; padding: 12px 16px; background: #f7f8fa; border-radius: 6px; }
.preview-box ul { margin: 8px 0 0; }
.daily-times-box { padding: 12px; margin-bottom: 12px; border: 1px solid #e5e7eb; border-radius: 6px; background: #f8fafc; }
.time-tags { display: flex; flex-wrap: wrap; gap: 8px; }
@media (max-width: 900px) { .page-heading, .table-toolbar { align-items: stretch; flex-direction: column; } .filter-actions { justify-content: flex-start; } }
</style>

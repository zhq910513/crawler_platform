<template>
  <div class="page-card task-schedule-page ops-task-page">
    <el-form class="ops-filter" label-position="left" label-width="86px">
      <div class="filter-grid">
        <el-form-item label="任务名称">
          <el-input v-model="query.taskName" clearable placeholder="请输入任务名称" @keyup.enter="search" />
        </el-form-item>
        <el-form-item label="采集入口">
          <el-input v-model="query.entryKeyword" clearable placeholder="请输入入口关键词" @keyup.enter="search" />
        </el-form-item>
        <el-form-item label="任务标识">
          <el-input v-model="query.taskCode" clearable placeholder="请输入任务标识" @keyup.enter="search" />
        </el-form-item>
        <el-form-item label="执行节点">
          <el-select v-model="query.serverId" clearable filterable placeholder="请选择执行节点">
            <el-option v-for="server in filteredServers" :key="server.serverId" :label="serverLabel(server)" :value="server.serverId" />
          </el-select>
        </el-form-item>
        <el-form-item label="任务组名">
          <el-input v-model="query.taskGroup" clearable placeholder="请选择任务组名" @keyup.enter="search" />
        </el-form-item>
        <el-form-item label="所属平台">
          <el-input v-model="query.taskPlatform" clearable placeholder="请选择所属平台" @keyup.enter="search" />
        </el-form-item>
        <el-form-item label="任务状态">
          <el-select v-model="query.taskStatus" clearable placeholder="请选择任务状态">
            <el-option v-for="item in taskStatusOptions" :key="item" :label="statusText(item)" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="开发人员">
          <el-select v-model="query.ownerUserId" clearable filterable placeholder="请选择开发人员" :disabled="!sessionState.user?.isSuperAdmin && !filteredOwnerUsers.length">
            <el-option v-for="user in filteredOwnerUsers" :key="user.userId" :label="user.nickName || user.userName" :value="user.userId" />
          </el-select>
        </el-form-item>
        <el-form-item label="最近结果">
          <el-select v-model="query.lastRunStatus" clearable placeholder="请选择状态">
            <el-option v-for="item in runStatusOptions" :key="item" :label="statusText(item)" :value="item" />
          </el-select>
        </el-form-item>
        <div class="filter-button-line">
          <el-button type="primary" :icon="Search" :loading="loading" @click="search">搜索</el-button>
          <el-button :icon="Refresh" @click="resetFilters">重置</el-button>
        </div>
      </div>
      <el-collapse v-model="advancedFilterNames" class="advanced-filter">
        <el-collapse-item name="advanced">
          <template #title>高级筛选（公司 / 项目 / 计划状态）</template>
          <div class="advanced-filter-grid">
            <el-form-item v-if="sessionState.user?.isSuperAdmin" label="公司">
              <el-select v-model="query.companyId" clearable filterable placeholder="全部公司" @change="handleCompanyChange">
                <el-option v-for="company in companies" :key="company.companyId" :label="company.companyName" :value="company.companyId" />
              </el-select>
            </el-form-item>
            <el-form-item v-else label="公司">
              <el-input :model-value="currentCompanyName" disabled />
            </el-form-item>
            <el-form-item label="项目">
              <el-select v-model="query.projectId" clearable filterable placeholder="全部项目">
                <el-option v-for="project in filteredProjects" :key="project.projectId" :label="project.projectName" :value="project.projectId" />
              </el-select>
            </el-form-item>
            <el-form-item label="计划状态">
              <el-select v-model="query.scheduleStatus" clearable placeholder="全部计划状态">
                <el-option v-for="item in scheduleStatusOptions" :key="item" :label="statusText(item)" :value="item" />
              </el-select>
            </el-form-item>
          </div>
        </el-collapse-item>
      </el-collapse>
    </el-form>


    <div v-if="pendingDefinitionTotal" class="discovered-task-card">
      <div class="discovered-task-header">
        <div>
          <div class="discovered-task-title">自动发现待编排任务 <el-tag type="warning" effect="light">{{ pendingDefinitionTotal }}</el-tag></div>
          <div class="cell-subtitle">项目发布后从 manifest.taskDefinitions 自动同步。这里只展示尚未创建正式任务的定义；完成配置、账号和计划后才进入正式任务列表。</div>
        </div>
      </div>
      <el-table :data="pendingDefinitions" size="small" class="discovered-task-table">
        <el-table-column label="项目" prop="projectName" min-width="120" show-overflow-tooltip />
        <el-table-column label="平台" min-width="88" show-overflow-tooltip><template #default="s">{{ s.row.platformCode || s.row.taskGroup || '-' }}</template></el-table-column>
        <el-table-column label="任务名称" prop="taskName" min-width="150" show-overflow-tooltip />
        <el-table-column label="任务标识" prop="definitionKey" min-width="150" show-overflow-tooltip />
        <el-table-column label="采集入口" prop="entryPath" min-width="190" show-overflow-tooltip />
        <el-table-column label="依赖" min-width="110" align="center">
          <template #default="s">
            <el-tag v-if="s.row.bindingRequired" type="warning" effect="light">需绑定 {{ bindingRequirementCount(s.row) }} 项</el-tag>
            <el-tag v-else type="success" effect="light">无外部绑定</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="契约" width="92" align="center"><template #default="s"><el-tag :type="s.row.contractStatus === 'OK' ? 'success' : 'warning'" effect="light">{{ s.row.contractStatus || 'UNKNOWN' }}</el-tag></template></el-table-column>
        <el-table-column label="操作" width="94" align="center" fixed="right"><template #default="s"><el-button link type="primary" @click="openPendingDefinition(s.row)">开始编排</el-button></template></el-table-column>
      </el-table>
    </div>

    <div class="ops-toolbar">
      <div class="ops-toolbar-left">
        <el-button type="primary" plain :icon="Plus" @click="openCreate">新增</el-button>
        <el-button type="success" plain :icon="Edit" :disabled="selectedRows.length !== 1" @click="editSelected">修改</el-button>
        <el-button type="danger" plain :icon="Delete" :disabled="!selectedRows.length" @click="disableSelected">删除</el-button>
        <el-button type="warning" plain :icon="Download" @click="exportRows">导出</el-button>
        <el-button plain :icon="Tickets" :disabled="selectedRows.length !== 1 || !selectedRows[0].lastRunId" @click="openLogsSelected">日志</el-button>
      </div>
      <div class="ops-toolbar-right">
        <el-tooltip content="搜索"><el-button circle :icon="Search" :loading="loading" @click="search" /></el-tooltip>
        <el-tooltip content="刷新"><el-button circle :icon="Refresh" :loading="loading" @click="loadPanel" /></el-tooltip>
      </div>
    </div>

    <el-table v-loading="loading" :data="rows" row-key="taskId" class="ops-table" @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="42" fixed="left" />
      <el-table-column label="任务号" prop="taskId" width="86" fixed="left" />
      <el-table-column label="执行节点" min-width="108" align="center" show-overflow-tooltip>
        <template #default="s">
          <div class="server-cell">{{ s.row.serverIp || s.row.serverName || '-' }}</div>
          <div v-if="s.row.serverIp && s.row.serverName" class="cell-subtitle">{{ s.row.serverName }}</div>
        </template>
      </el-table-column>
      <el-table-column label="所属平台" min-width="92" align="center" show-overflow-tooltip>
        <template #default="s">{{ s.row.taskPlatform || s.row.projectName || '-' }}</template>
      </el-table-column>
      <el-table-column label="任务名称" prop="taskName" min-width="130" show-overflow-tooltip />
      <el-table-column label="最近完成" min-width="138" align="center">
        <template #default="s">{{ formatTime(s.row.lastFinishedAt) }}</template>
      </el-table-column>
      <el-table-column label="执行计划" min-width="118" align="center" show-overflow-tooltip>
        <template #default="s">{{ cronText(s.row) }}</template>
      </el-table-column>
      <el-table-column label="下次执行时间" min-width="138" align="center">
        <template #default="s">{{ formatTime(s.row.nextRunAt) }}</template>
      </el-table-column>
      <el-table-column label="开发人员" min-width="86" align="center">
        <template #default="s">{{ s.row.ownerUserName || '-' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="82" align="center">
        <template #default="s">
          <el-tooltip :content="s.row.taskStatus === 'ENABLED' ? '任务已启用' : '任务已停用'">
            <el-switch :model-value="s.row.taskStatus === 'ENABLED'" @change="toggleTaskStatus(s.row, Boolean($event))" />
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="最近结果" width="98" align="center">
        <template #default="s"><el-tag :type="runTagType(s.row.lastRunStatus)" effect="light">{{ statusText(s.row.lastRunStatus) }}</el-tag></template>
      </el-table-column>
      <el-table-column label="操作" width="152" align="center" fixed="right">
        <template #default="s">
          <el-tooltip content="编辑"><el-button link type="primary" :icon="Edit" @click="openEdit(s.row)" /></el-tooltip>
          <el-tooltip content="删除"><el-button link type="primary" :icon="Delete" @click="disableRow(s.row)" /></el-tooltip>
          <el-tooltip content="立即执行"><el-button link type="primary" :icon="VideoPlay" @click="manualRun(s.row)" /></el-tooltip>
          <el-tooltip content="查看"><el-button link type="primary" :icon="View" @click="openDetail(s.row)" /></el-tooltip>
          <el-tooltip content="计划设置"><el-button link type="primary" :icon="Operation" @click="openSchedule(s.row)" /></el-tooltip>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-wrap">
      <el-pagination v-model:current-page="query.page" v-model:page-size="query.pageSize" :page-sizes="[20, 50, 100, 200]" :total="total" layout="total, sizes, prev, pager, next, jumper" @current-change="loadPanel" @size-change="handlePageSizeChange" />
    </div>

    <el-dialog v-model="createVisible" title="新增任务" width="840px" destroy-on-close>
      <el-form label-position="top">
        <el-row :gutter="16">
          <el-col :span="12" v-if="sessionState.user?.isSuperAdmin"><el-form-item label="所属公司" required><el-select v-model="createContext.companyId" filterable @change="loadCreateProjects"><el-option v-for="company in companies" :key="company.companyId" :label="company.companyName" :value="company.companyId" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="所属项目" required><el-select v-model="createContext.projectId" filterable @change="loadCreateResources"><el-option v-for="project in createProjects" :key="project.projectId" :label="project.projectName" :value="project.projectId" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="平台任务" required><el-select v-model="createForm.definitionId" filterable @change="applyDefinition"><el-option v-for="definition in definitions" :key="definition.definitionId" :label="definition.taskName" :value="definition.definitionId" :disabled="definition.definitionStatus !== 'AVAILABLE'" /></el-select></el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="任务标识" required><el-input v-model="createForm.taskCode" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="任务名称" required><el-input v-model="createForm.taskName" /></el-form-item></el-col>
          <el-col v-if="sessionState.user?.isSuperAdmin" :span="12"><el-form-item label="负责人"><el-select v-model="createForm.ownerUserId" clearable filterable><el-option v-for="user in createOwnerUsers" :key="user.userId" :label="user.nickName || user.userName" :value="user.userId" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="任务状态"><el-select v-model="createForm.status"><el-option label="启用" value="ENABLED" /><el-option label="草稿" value="DRAFT" /><el-option label="暂停" value="PAUSED" /></el-select></el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8"><el-form-item label="调度类型"><el-select v-model="createForm.scheduleType"><el-option label="手动" value="MANUAL" /><el-option label="定时" value="CRON" /></el-select></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="计划状态"><el-select v-model="createForm.scheduleStatus"><el-option label="启用" value="ENABLED" /><el-option label="暂停" value="PAUSED" /><el-option label="停用" value="DISABLED" /></el-select></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="任务组"><el-input v-model="createForm.taskGroup" /></el-form-item></el-col>
        </el-row>
        <el-form-item v-if="createForm.scheduleType === 'CRON'" label="高级表达式"><el-input v-model="createForm.cronExpression" placeholder="5 段格式：分钟 小时 日 月 星期" /></el-form-item>
        <el-form-item label="指定执行节点"><el-select v-model="createForm.serverIds" multiple clearable filterable placeholder="为空时使用项目默认节点"><el-option v-for="server in createProjectServers" :key="server.serverId" :label="server.serverName || String(server.serverId)" :value="server.serverId" /></el-select></el-form-item>
        <div v-if="createConfigRequirements.length" class="binding-box">
          <div class="binding-title">运行配置绑定</div>
          <el-form-item v-for="requirement in createConfigRequirements" :key="String(requirement.slot)" :label="configRequirementLabel(requirement)" :required="Boolean(requirement.required)">
            <el-select v-model="createConfigBindings[String(requirement.slot)]" clearable filterable placeholder="选择已验证的公司数据资源">
              <el-option v-for="resource in resourcesForRequirement(requirement)" :key="resource.resourceId" :label="`${resource.resourceName}（${resource.resourceCode} / ${resource.resourceEngine}）`" :value="resource.resourceId" />
            </el-select>
          </el-form-item>
          <div v-if="createConfigRequirements.some((item) => resourcesForRequirement(item).length === 0)" class="cell-subtitle">没有匹配且已验证的数据资源时，请先到“数据资源配置”完成资源新增和校验。</div>
        </div>
        <el-alert v-if="createCredentialRequirements.length" type="warning" :closable="false" show-icon title="该任务声明了平台账号绑定要求；请先确认平台账号资源已准备。" />
        <el-collapse>
          <el-collapse-item title="高级执行配置" name="advanced">
            <el-row :gutter="16">
              <el-col :span="8"><el-form-item label="运行模式"><el-select v-model="createForm.runtimeMode"><el-option label="标准容器" value="SHARED_ENV_ISOLATED" /><el-option label="常驻服务" value="WORKER_POOL" /><el-option label="独占容器" value="DEDICATED_CONTAINER" /></el-select></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="单任务同时运行上限"><el-input-number v-model="createForm.taskMaxConcurrency" :min="1" :max="1000" /></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="任务组同时运行上限"><el-input-number v-model="createForm.groupMaxConcurrency" :min="1" :max="1000" /></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="内存共享"><el-input-number v-model="createForm.shmSizeMb" :min="16" :max="65536" /></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="日志上限 MB"><el-input-number v-model="createForm.logLimitMb" :min="1" :max="10240" /></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="独占运行"><el-switch v-model="createForm.exclusiveMode" /></el-form-item></el-col>
            </el-row>
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

    <el-dialog v-model="scheduleVisible" title="修改任务编排" width="860px">
      <el-form label-position="top" class="schedule-form">
        <el-row :gutter="16">
          <el-col :span="8"><el-form-item label="计划状态"><el-select v-model="scheduleForm.scheduleStatus"><el-option label="启用" value="ENABLED" /><el-option label="暂停" value="PAUSED" /><el-option label="停用" value="DISABLED" /></el-select></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="调度类型"><el-select v-model="scheduleForm.scheduleType"><el-option label="手动" value="MANUAL" /><el-option label="定时" value="CRON" /></el-select></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="重叠策略"><el-select v-model="scheduleForm.overlapPolicy"><el-option label="排队等待" value="QUEUE" /><el-option label="跳过新触发" value="SKIP" /><el-option label="允许并发" value="CONCURRENT" /><el-option label="取消旧任务" value="CANCEL_OLD" /></el-select></el-form-item></el-col>
        </el-row>
        <template v-if="scheduleForm.scheduleType === 'CRON'">
          <el-form-item label="快捷设置">
            <el-radio-group v-model="scheduleMode" @change="applyScheduleMode">
              <el-radio-button label="EVERY_N_MINUTES">每 N 分钟</el-radio-button><el-radio-button label="EVERY_N_HOURS">每 N 小时</el-radio-button><el-radio-button label="DAILY">每天</el-radio-button><el-radio-button label="DAILY_TIMES">每天多时间点</el-radio-button><el-radio-button label="WEEKLY">每周</el-radio-button><el-radio-button label="WEEKLY_TIMES">每周多日期/时间</el-radio-button><el-radio-button label="MONTHLY">每月</el-radio-button><el-radio-button label="MONTHLY_TIMES">每月多日期/时间</el-radio-button><el-radio-button label="ADVANCED">高级排程</el-radio-button>
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
          <el-form-item label="高级表达式"><el-input v-model="scheduleForm.cronExpression" @input="scheduleMode = 'ADVANCED'" /></el-form-item>
          <el-form-item label="时区"><el-input v-model="scheduleForm.scheduleTimezone" /></el-form-item>
          <el-button @click="loadCronPreview">校验并预览最近 5 次</el-button>
          <div class="preview-box"><div class="cell-subtitle">最近 5 次预计执行时间</div><ul><li v-for="item in cronPreview" :key="item">{{ item }}</li></ul></div>
        </template>
      </el-form>
      <template #footer><el-button @click="scheduleVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveSchedule">保存调度</el-button></template>
    </el-dialog>

    <el-drawer v-model="detailVisible" title="任务编排详情" size="620px">
      <el-descriptions v-if="detailRow" :column="1" border>
        <el-descriptions-item label="公司 / 项目">{{ detailRow.companyName }} / {{ detailRow.projectName }}</el-descriptions-item>
        <el-descriptions-item label="任务">{{ detailRow.taskName }}</el-descriptions-item>
        <el-descriptions-item label="执行节点">{{ detailRow.serverName || '-' }} {{ detailRow.serverIp || '' }}</el-descriptions-item>
        <el-descriptions-item label="负责人">{{ detailRow.ownerUserName || '-' }}</el-descriptions-item>
        <el-descriptions-item label="调度">{{ scheduleText(detailRow) }}</el-descriptions-item>
        <el-descriptions-item label="时区">{{ detailRow.scheduleTimezone || '-' }}</el-descriptions-item>
        <el-descriptions-item label="下次执行">{{ formatTime(detailRow.nextRunAt) }}</el-descriptions-item>
        <el-descriptions-item label="最近结果">{{ statusText(detailRow.lastRunStatus) }}</el-descriptions-item>
        <el-descriptions-item label="分配状态">{{ statusText(detailRow.routingStatus) }}</el-descriptions-item>
        <el-descriptions-item label="最近完成">{{ formatTime(detailRow.lastFinishedAt) }}</el-descriptions-item>
        <el-descriptions-item label="最近错误">{{ detailRow.lastErrorSummary || '-' }}</el-descriptions-item>
      </el-descriptions>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Download, Edit, Operation, Plus, Refresh, Search, Tickets, VideoPlay, View } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { createRun, createTask, deleteTask, listCompanies, listCompanyResourceConfigs, listProjectServers, listProjects, listServers, listTaskDefinitions, listTasks, listUsers, previewCronExpression, updateTask, updateTaskSchedule } from '../api/platform'
import { listTaskSchedulePanels } from '../api/taskSchedules'
import { sessionState } from '../stores/session'
import type { Company, CompanyResourceConfig, PendingTaskDefinitionItem, Project, ProjectServer, ScheduleUpdateRequest, ServerNode, Task, TaskCreateRequest, TaskDefinition, TaskSchedulePanelItem, TaskUpdateRequest, UserAccount } from '../types/api'
import { formatTime } from '../utils/dictionaries'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const saving = ref(false)
const rows = ref<TaskSchedulePanelItem[]>([])
const pendingDefinitions = ref<PendingTaskDefinitionItem[]>([])
const pendingDefinitionTotal = ref(0)
const selectedRows = ref<TaskSchedulePanelItem[]>([])
const total = ref(0)
const advancedFilterNames = ref<string[]>([])
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
const createResources = ref<CompanyResourceConfig[]>([])
const createConfigBindings = reactive<Record<string, number | undefined>>({})
const createParamsText = ref('{}')
const createLocksText = ref('')
const createForm = reactive<TaskCreateRequest>({ definitionId: 0, ownerUserId: null, taskCode: '', taskName: '', parameters: {}, status: 'ENABLED', imagePolicy: 'RELEASE_CHANNEL', releaseChannel: 'stable', scheduleStatus: 'PAUSED', scheduleType: 'MANUAL', cronExpression: '', scheduleTimezone: 'Asia/Shanghai', overlapPolicy: 'QUEUE', scheduleConfig: {}, scheduleLabel: '', serverIds: [], runtimeMode: 'SHARED_ENV_ISOLATED', taskGroup: 'default', taskMaxConcurrency: 1, groupMaxConcurrency: 4, exclusiveMode: false, ioClass: 'NORMAL', shmSizeMb: 64, logLimitMb: 50, resourceLocks: [] })
const createOwnerUsers = computed(() => ownerUsers.value.filter((item) => item.companyId === createContext.companyId && item.status === 'ENABLED'))
const selectedCreateDefinition = computed(() => definitions.value.find((item) => item.definitionId === createForm.definitionId) || null)
const createConfigRequirements = computed(() => (selectedCreateDefinition.value?.requiredConfigs || []).filter((item) => String(item.slot || '').trim()))
const createCredentialRequirements = computed(() => (selectedCreateDefinition.value?.requiredCredentials || []).filter((item) => String(item.slot || '').trim()))

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
  const map: Record<string, string> = { ENABLED: '启用', DISABLED: '停用', PAUSED: '暂停', DRAFT: '草稿', ARCHIVED: '归档', ERROR: '异常', NONE: '无自动计划', QUEUED: '排队中', ROUTED: '已分配', RUNNING: '运行中', STARTING: '启动中', ASSIGNED: '已分配', SUCCEEDED: '成功', FAILED: '失败', CANCELED: '已取消', CANCELLED: '已取消', TIMED_OUT: '超时', TIMEOUT: '超时', LOST: '失联', NOT_RUN: '未运行', WAITING_RESOURCE: '等待资源', NO_AVAILABLE_SERVER: '无可用节点', PENDING: '待处理' }
  return value ? (map[value] || value) : '-'
}
type TagType = '' | 'primary' | 'success' | 'warning' | 'info' | 'danger'
function taskTagType(status: string): TagType { if (status === 'ENABLED') return 'success'; if (status === 'DISABLED' || status === 'ARCHIVED') return 'info'; if (status === 'PAUSED') return 'warning'; return '' }
function runTagType(status: string): TagType { if (status === 'SUCCEEDED') return 'success'; if (['FAILED', 'TIMED_OUT', 'TIMEOUT', 'LOST', 'CANCELED', 'CANCELLED'].includes(status)) return 'danger'; if (['RUNNING', 'STARTING', 'ASSIGNED', 'ROUTED'].includes(status)) return 'primary'; if (['QUEUED', 'WAITING_RESOURCE'].includes(status)) return 'warning'; return 'info' }
function scheduleText(row: TaskSchedulePanelItem) { if (row.scheduleType !== 'CRON') return '手动执行'; return row.scheduleLabel || row.cronExpression || '-' }
function cronText(row: TaskSchedulePanelItem) { return row.cronExpression || row.scheduleLabel || '-' }
function handleSelectionChange(selection: TaskSchedulePanelItem[]) { selectedRows.value = selection }
function assertSingleSelection(actionName: string) { if (selectedRows.value.length !== 1) { ElMessage.warning(`请先选择一条任务再${actionName}`); return null } return selectedRows.value[0] }

async function loadOptions() {
  const [companyRows, projectRows, serverRows] = await Promise.all([listCompanies(), listProjects(), listServers()])
  companies.value = companyRows
  projects.value = projectRows
  servers.value = serverRows
  const qCompany = Number(route.query.companyId || 0) || undefined
  if (sessionState.user?.isSuperAdmin && qCompany) query.companyId = qCompany
  if (!sessionState.user?.isSuperAdmin) query.companyId = sessionState.user?.companyId || undefined
  if (sessionState.user?.isSuperAdmin) ownerUsers.value = await listUsers()
}
async function loadPanel() {
  loading.value = true
  try {
    const result = await listTaskSchedulePanels({ ...query, companyId: effectiveCompanyId.value, taskName: query.taskName || undefined, taskCode: query.taskCode || undefined, entryKeyword: query.entryKeyword || undefined, taskGroup: query.taskGroup || undefined, taskPlatform: query.taskPlatform || undefined, taskStatus: query.taskStatus || undefined, scheduleStatus: query.scheduleStatus || undefined, lastRunStatus: query.lastRunStatus || undefined })
    rows.value = result.items
    pendingDefinitions.value = result.pendingDefinitions || []
    pendingDefinitionTotal.value = result.pendingDefinitionTotal || 0
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
  for (const key of Object.keys(createConfigBindings)) delete createConfigBindings[key]
}
async function openCreate() {
  resetCreateForm()
  createContext.companyId = sessionState.user?.isSuperAdmin ? (query.companyId || companies.value[0]?.companyId) : sessionState.user?.companyId || undefined
  createVisible.value = true
  await loadCreateProjects()
}
async function openPendingDefinition(row: PendingTaskDefinitionItem) {
  resetCreateForm()
  createContext.companyId = row.companyId
  createVisible.value = true
  const all = await listProjects(row.companyId)
  createProjects.value = all.filter((item) => item.companyId === row.companyId)
  createContext.projectId = row.projectId
  await loadCreateResources()
  const discovered = definitions.value.find((item) => item.definitionId === row.definitionId && item.definitionStatus === 'AVAILABLE')
  if (!discovered) {
    ElMessage.warning('该任务定义已变化，请刷新任务编排页面后重试')
    return
  }
  createForm.definitionId = discovered.definitionId
  applyDefinition()
}
function bindingRequirementCount(row: PendingTaskDefinitionItem) {
  return (row.requiredConfigs?.length || 0) + (row.requiredCredentials?.length || 0)
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
  const [definitionRows, serverRows, resourceRows] = await Promise.all([listTaskDefinitions(createContext.projectId), listProjectServers(createContext.projectId), listCompanyResourceConfigs({ companyId: createContext.companyId })])
  definitions.value = definitionRows
  createProjectServers.value = serverRows.filter((item) => item.deploymentStatus === 'DEPLOYED' && item.schedulingStatus !== 'DISABLED')
  createResources.value = resourceRows.filter((item) => !item.projectId || item.projectId === createContext.projectId)
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
  for (const key of Object.keys(createConfigBindings)) delete createConfigBindings[key]
  for (const requirement of row.requiredConfigs || []) {
    const slot = String(requirement.slot || '').trim()
    if (!slot) continue
    const candidates = resourcesForRequirement(requirement)
    if (candidates.length === 1) createConfigBindings[slot] = candidates[0].resourceId
  }
}
function normalizedRequirementEngine(requirement: Record<string, unknown>) {
  const value = String(requirement.type || requirement.configType || requirement.resourceEngine || '').trim().toUpperCase()
  const aliases: Record<string, string> = { MONGO: 'MONGODB', POSTGRES: 'POSTGRESQL', SQL_SERVER: 'SQLSERVER', OSS: 'ALIYUN_OSS' }
  return aliases[value] || value
}
function resourcesForRequirement(requirement: Record<string, unknown>) {
  const engine = normalizedRequirementEngine(requirement)
  return createResources.value.filter((item) => item.enabled && ['CONFIG_VALID', 'CONNECTION_PASSED', 'MANUAL_CONFIRMED'].includes(item.testStatus) && (!engine || item.resourceEngine === engine))
}
function configRequirementLabel(requirement: Record<string, unknown>) {
  const slot = String(requirement.slot || '')
  const description = String(requirement.description || '')
  return description ? `${slot} · ${description}` : slot
}
async function saveTask() {
  if (!createContext.projectId || !createForm.definitionId) { ElMessage.warning('请选择项目和可创建的平台任务'); return }
  let parameters: Record<string, unknown>
  try { parameters = JSON.parse(createParamsText.value || '{}') } catch { ElMessage.error('运行参数格式不正确'); return }
  saving.value = true
  try {
    createForm.parameters = parameters
    createForm.resourceLocks = createLocksText.value.split(',').map((item) => item.trim()).filter(Boolean)
    const configBindings: Record<string, unknown> = {}
    for (const requirement of createConfigRequirements.value) {
      const slot = String(requirement.slot || '').trim()
      const resourceId = createConfigBindings[slot]
      if (Boolean(requirement.required) && !resourceId) { ElMessage.warning(`请绑定必需配置：${slot}`); return }
      if (!resourceId) continue
      const resource = createResources.value.find((item) => item.resourceId === resourceId)
      if (!resource) { ElMessage.warning(`配置绑定已失效：${slot}`); return }
      configBindings[slot] = { resourceId: resource.resourceId, resourceCode: resource.resourceCode }
    }
    createForm.configBindings = configBindings
    if (createCredentialRequirements.value.length) { ElMessage.warning('当前任务声明了账号绑定要求，请先在平台账号中完成账号准备后再创建；账号绑定编排将在后续版本继续完善。'); return }
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
async function toggleTaskStatus(row: TaskSchedulePanelItem, enabled: boolean) {
  const nextStatus = enabled ? 'ENABLED' : 'DISABLED'
  const message = enabled ? `确认启用任务“${row.taskName}”？` : `确认停用任务“${row.taskName}”？停用后不会自动运行。`
  try {
    await ElMessageBox.confirm(message, enabled ? '启用任务' : '停用任务', { type: 'warning' })
    await updateTask(row.taskId, { status: nextStatus })
    ElMessage.success(enabled ? '任务已启用' : '任务已停用')
    await loadPanel()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') throw error
  }
}
async function disableRow(row: TaskSchedulePanelItem) {
  try {
    await ElMessageBox.confirm(`确认删除任务“${row.taskName}”？没有历史记录的任务会被删除；已有历史记录的任务会归档并停用自动计划。`, '删除确认', { type: 'warning' })
    const result = await deleteTask(row.taskId)
    const cleanupCount = result.containerCleanupCommands?.length || 0
    ElMessage.success(result.deleted ? `任务已删除，已下发 ${cleanupCount} 条容器清理指令` : `任务已有历史执行记录，已归档隐藏，并下发 ${cleanupCount} 条容器清理指令`)
    await loadPanel()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(error instanceof Error ? error.message : '删除任务失败')
  }
}
async function disableSelected() {
  if (!selectedRows.value.length) { ElMessage.warning('请先选择要删除的任务'); return }
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selectedRows.value.length} 个任务？没有历史记录的任务会被删除；已有历史记录的任务会归档并停用自动计划。`, '批量删除确认', { type: 'warning' })
    let deleted = 0
    let archived = 0
    for (const row of selectedRows.value) {
      const result = await deleteTask(row.taskId)
      if (result.deleted) deleted += 1
      else if (result.archived) archived += 1
    }
    ElMessage.success(`删除完成：物理删除 ${deleted} 个，归档隐藏 ${archived} 个；容器清理指令由对应执行节点心跳处理`)
    selectedRows.value = []
    await loadPanel()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(error instanceof Error ? error.message : '批量删除任务失败')
  }
}
function editSelected() { const row = assertSingleSelection('修改'); if (row) void openEdit(row) }
function openLogsSelected() { const row = assertSingleSelection('查看日志'); if (row) void openLogs(row) }
function exportRows() {
  const headers = ['任务号', '执行节点', '所属平台', '任务名称', '最近完成', '执行计划', '下次执行时间', '开发人员', '状态', '最近结果']
  const source = selectedRows.value.length ? selectedRows.value : rows.value
  const lines = [headers, ...source.map((row) => [row.taskId, row.serverIp || row.serverName || '', row.taskPlatform || row.projectName || '', row.taskName, formatTime(row.lastFinishedAt), cronText(row), formatTime(row.nextRunAt), row.ownerUserName || '', statusText(row.taskStatus), statusText(row.lastRunStatus)])]
  const csv = lines.map((line) => line.map((cell) => `"${String(cell ?? '').replace(/"/g, '""')}"`).join(',')).join('\n')
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `task-schedules-${new Date().toISOString().slice(0, 10)}.csv`
  link.click()
  URL.revokeObjectURL(url)
}
async function toggleSchedule(row: TaskSchedulePanelItem, enabled: boolean) {
  const message = enabled ? '确认启用该任务自动计划？' : '确认停用后该任务不会自动运行，但仍可手动执行。'
  try {
    await ElMessageBox.confirm(message, enabled ? '启用计划' : '停用计划', { type: 'warning' })
    await updateTaskSchedule(row.taskId, { scheduleStatus: enabled ? 'ENABLED' : 'DISABLED' })
    ElMessage.success(enabled ? '计划已启用' : '计划已停用')
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
.task-schedule-page { min-width: 0; background: #fff; }
.ops-task-page { padding: 14px 16px 18px; }
.ops-filter { margin-bottom: 8px; }
.filter-grid { display: grid; grid-template-columns: repeat(5, minmax(180px, 1fr)); column-gap: 12px; row-gap: 8px; align-items: center; }
.filter-grid :deep(.el-form-item) { margin-bottom: 0; }
.filter-grid :deep(.el-form-item__label), .advanced-filter-grid :deep(.el-form-item__label) { height: 32px; line-height: 32px; padding-right: 6px; color: #303b4d; font-size: 13px; font-weight: 600; white-space: nowrap; }
.filter-grid :deep(.el-input__wrapper), .filter-grid :deep(.el-select__wrapper), .advanced-filter-grid :deep(.el-input__wrapper), .advanced-filter-grid :deep(.el-select__wrapper) { min-height: 32px; border-radius: 4px; box-shadow: 0 0 0 1px #d7deea inset; }
.filter-grid :deep(.el-select), .filter-grid :deep(.el-input), .advanced-filter-grid :deep(.el-select), .advanced-filter-grid :deep(.el-input) { width: 100%; }
.filter-grid :deep(.el-input__inner), .filter-grid :deep(.el-select__placeholder), .advanced-filter-grid :deep(.el-input__inner), .advanced-filter-grid :deep(.el-select__placeholder) { font-size: 13px; }
.filter-button-line { display: flex; align-items: center; gap: 8px; min-height: 32px; }
.filter-button-line :deep(.el-button) { height: 32px; padding: 0 14px; font-size: 13px; }
.advanced-filter { margin-top: 6px; border: 0; }
.advanced-filter :deep(.el-collapse-item__header) { height: 30px; color: #6b7280; border-bottom: 0; font-size: 12px; }
.advanced-filter :deep(.el-collapse-item__wrap) { border-bottom: 0; }
.advanced-filter-grid { display: grid; grid-template-columns: repeat(4, minmax(180px, 1fr)); column-gap: 12px; row-gap: 8px; padding: 4px 0 0; }
.advanced-filter-grid :deep(.el-form-item) { margin-bottom: 0; }

.discovered-task-card { margin: 8px 0 10px; padding: 10px 12px 12px; border: 1px solid #f0c36d; border-radius: 6px; background: #fffaf0; }
.discovered-task-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.discovered-task-title { display: flex; align-items: center; gap: 8px; color: #7a4f01; font-size: 14px; font-weight: 700; }
.discovered-task-table { width: 100%; }
.discovered-task-table :deep(.el-table__header th) { background: #fff7e6; }

.ops-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin: 6px 0 8px; }
.ops-toolbar-left, .ops-toolbar-right { display: flex; align-items: center; gap: 8px; }
.ops-toolbar-left :deep(.el-button) { height: 32px; padding: 0 12px; border-radius: 4px; font-size: 13px; }
.ops-toolbar-right :deep(.el-button) { width: 32px; height: 32px; }
.ops-table { width: 100%; border-top: 0; color: #2f3a4b; font-size: 13px; }
.ops-table :deep(.el-table__header th) { height: 42px; background: #f6f7f9; color: #243047; font-size: 13px; font-weight: 700; white-space: nowrap; }
.ops-table :deep(.el-table__row td) { height: 46px; border-bottom: 1px solid #e8edf5; }
.ops-table :deep(.el-table__cell) { padding: 3px 0; }
.ops-table :deep(.cell) { line-height: 18px; white-space: nowrap; }
.ops-table :deep(.el-button.is-link) { padding: 2px 4px; font-size: 14px; }
.ops-table :deep(.el-tag) { height: 22px; padding: 0 6px; font-size: 12px; }
.server-cell { overflow: hidden; line-height: 18px; white-space: nowrap; text-overflow: ellipsis; }
.cell-subtitle { overflow: hidden; margin-top: 1px; color: #8a94a6; font-size: 11px; line-height: 15px; white-space: nowrap; text-overflow: ellipsis; }
.pagination-wrap { display: flex; justify-content: flex-end; margin-top: 10px; }
.binding-box { padding: 10px 12px 2px; margin-bottom: 12px; border: 1px solid #d9e2f2; border-radius: 6px; background: #f8fbff; }
.binding-title { margin-bottom: 8px; color: #30456b; font-size: 13px; font-weight: 700; }
.schedule-form { margin-top: 16px; }
.preview-box { margin-top: 12px; padding: 12px 16px; background: #f7f8fa; border-radius: 6px; }
.preview-box ul { margin: 8px 0 0; }
.daily-times-box { padding: 12px; margin-bottom: 12px; border: 1px solid #e5e7eb; border-radius: 6px; background: #f8fafc; }
.time-tags { display: flex; flex-wrap: wrap; gap: 8px; }
@media (max-width: 1280px) { .filter-grid { grid-template-columns: repeat(3, minmax(180px, 1fr)); } .advanced-filter-grid { grid-template-columns: repeat(3, minmax(180px, 1fr)); } }
@media (max-width: 760px) { .ops-task-page { padding: 12px; } .filter-grid, .advanced-filter-grid { grid-template-columns: 1fr; row-gap: 8px; } .ops-toolbar { align-items: stretch; flex-direction: column; } .ops-toolbar-left { flex-wrap: wrap; } }
</style>

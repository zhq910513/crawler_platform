<template>
  <div class="page-card">
    <div class="toolbar">
      <el-select v-if="sessionState.user?.isSuperAdmin" v-model="selectedCompanyId" placeholder="选择公司" clearable style="width: 220px" @change="loadAll">
        <el-option v-for="company in companies" :key="company.companyId" :label="company.companyName" :value="company.companyId" />
      </el-select>
      <span v-else class="muted">当前公司：{{ currentCompanyName }}</span>
      <el-button type="primary" @click="openImport">接入已有版本</el-button>
      <el-button disabled title="平台构建中心尚未就绪">构建中心未就绪</el-button>
      <el-button @click="loadAll">刷新</el-button>
    </div>

    <el-table :data="projects" border @row-click="selectProject">
      <el-table-column label="项目名称" prop="projectName" min-width="150" />
            <el-table-column label="备注" prop="remark" min-width="160" />
      <el-table-column label="上线状态"><template #default="s">{{ zh(s.row.onlineStatus) }}</template></el-table-column>
      <el-table-column label="最新版本" prop="latestVersion" />
      <el-table-column label="部署节点数" prop="deployedServerCount" />
      <el-table-column label="启用节点数" prop="executionServerCount" />
      <el-table-column label="运行模式"><template #default="s">{{ zh(s.row.dispatchMode) }}</template></el-table-column>
      <el-table-column label="创建时间"><template #default="s">{{ formatTime(s.row.createdAt) }}</template></el-table-column>
      <el-table-column label="操作" width="180" fixed="right"><template #default="s"><el-button size="small" type="primary" link @click.stop="oneClickDeploy(s.row)">部署当前版本</el-button><el-button size="small" type="danger" link @click.stop="deleteProjectRow(s.row)">删除</el-button></template></el-table-column>
    </el-table>

    <el-divider />
    <section v-if="selectedProject">
      <div class="section-title">
        <h3>部署与节点：{{ selectedProject.projectName }}</h3>
        <div><el-button size="small" type="primary" @click="oneClickDeploy(selectedProject)">部署当前版本</el-button><el-button size="small" @click="openServerPoolEditor">配置节点</el-button><el-button size="small" @click="refreshSelectedProject">刷新</el-button></div>
      </div>
      <el-table :data="projectServers" border>
        <el-table-column label="节点名称" prop="serverName" />
                <el-table-column label="部署状态"><template #default="s">{{ zh(s.row.deploymentStatus) }}</template></el-table-column>
        <el-table-column label="接收任务"><template #default="s">{{ zh(s.row.schedulingStatus) }}</template></el-table-column>
        <el-table-column label="镜像状态"><template #default="s">{{ zh(s.row.imageReadinessStatus) }}</template></el-table-column>
        <el-table-column label="角色"><template #default="s">{{ zh(s.row.serverRole) }}</template></el-table-column>
        <el-table-column label="健康"><template #default="s">{{ zh(s.row.healthStatus || '') }}</template></el-table-column>
        <el-table-column label="负载"><template #default="s">{{ zh(s.row.capacityStatus || '') }}</template></el-table-column>
        <el-table-column label="任务上限" prop="maxConcurrency" />
        <el-table-column label="暂停原因" prop="disabledReason" min-width="180" />
      </el-table>
      <el-divider />
      <h3>最近部署单</h3>
      <el-table :data="deploymentHistory" border>
        <el-table-column label="部署单" prop="deploymentName" min-width="180" />
        <el-table-column label="状态"><template #default="s">{{ zh(s.row.deploymentStatus) }}</template></el-table-column>
        <el-table-column label="目标数"><template #default="s">{{ Array.isArray(s.row.targets) ? s.row.targets.length : 0 }}</template></el-table-column>
        <el-table-column label="步骤" min-width="260"><template #default="s"><span>{{ deploymentStepText(s.row) }}</span></template></el-table-column>
        <el-table-column label="创建时间"><template #default="s">{{ formatTime(s.row.createdAt) }}</template></el-table-column>
      </el-table>
    </section>

    <el-dialog v-model="importVisible" title="接入已有版本" width="900px">
      <div class="toolbar">
        <el-select v-if="sessionState.user?.isSuperAdmin" v-model="importCompanyId" placeholder="选择公司" style="width: 260px" @change="loadDiscovered">
          <el-option v-for="company in companies" :key="company.companyId" :label="company.companyName" :value="company.companyId" />
        </el-select>
        <span v-else class="muted">当前公司：{{ currentCompanyName }}</span>
        <el-button @click="loadDiscovered">刷新待接入已有版本</el-button>
      </div>
      <el-table :data="discoveredProjects" border :row-class-name="discoveredRowClass" @row-click="setDiscovered">
        <el-table-column label="项目名称" prop="projectName" />
                <el-table-column label="最新版本" prop="latestVersion" />
        <el-table-column label="部署节点数" prop="deploymentServerCount" />
        <el-table-column label="状态"><template #default="s">{{ s.row.selectable ? '待接入' : zh(s.row.discoveryStatus) }}</template></el-table-column>
        <el-table-column label="最近部署"><template #default="s">{{ formatTime(s.row.lastDeployedAt) }}</template></el-table-column>
      </el-table>
      <el-form label-position="top" style="margin-top: 14px">
        <el-form-item label="备注"><el-input v-model="importForm.remark" /></el-form-item>
        <el-form-item label="运行模式"><el-select v-model="importForm.dispatchMode"><el-option label="负载均衡" value="LOAD_BALANCE" /><el-option label="主备模式" value="PRIMARY_STANDBY" /></el-select></el-form-item>
      </el-form>
      <template #footer><el-button @click="importVisible = false">取消</el-button><el-button type="primary" :disabled="!selectedDiscovered?.selectable" @click="submitImport">确认接入</el-button></template>
    </el-dialog>

    <el-dialog v-model="serverPoolVisible" title="配置节点" width="1080px">
      <el-table :data="serverPoolDraft" border>
        <el-table-column label="启用" width="70"><template #default="s"><el-checkbox v-model="s.row.enabled" /></template></el-table-column>
        <el-table-column label="执行节点" min-width="170"><template #default="s">{{ s.row.serverName }}</template></el-table-column>
        <el-table-column label="接入状态" width="100"><template #default="s">{{ s.row.projectServerId ? '已加入' : '未加入' }}</template></el-table-column>
        <el-table-column label="接收任务" width="140"><template #default="s"><el-select v-model="s.row.schedulingStatus"><el-option label="可接收任务" value="ENABLED" /><el-option label="暂停接收新任务" value="DRAINING" /><el-option label="暂停" value="PAUSED" /><el-option label="禁用" value="DISABLED" /></el-select></template></el-table-column>
        <el-table-column label="角色" width="140"><template #default="s"><el-select v-model="s.row.serverRole"><el-option label="活动节点" value="ACTIVE" /><el-option label="主节点" value="PRIMARY" /><el-option label="备用节点" value="STANDBY" /><el-option label="候选节点" value="CANDIDATE" /></el-select></template></el-table-column>
        <el-table-column label="任务上限" width="130"><template #default="s"><el-input-number v-model="s.row.maxConcurrency" :min="1" /></template></el-table-column>
      </el-table>
      <el-form label-position="top" style="margin-top: 14px"><el-form-item label="调整原因"><el-input v-model="serverPoolReason" /></el-form-item></el-form>
      <div v-if="poolAnalysis" class="soft-panel">影响分析已完成，请确认后保存。</div>
      <template #footer><el-button @click="serverPoolVisible = false">取消</el-button><el-button @click="analyzePool">影响分析</el-button><el-button @click="deploySelectedRelease">部署当前版本</el-button><el-button type="primary" @click="savePool">保存</el-button></template>
    </el-dialog>

  </div>
</template>
<script setup lang="ts">
import { computed, onActivated, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import { analyzeProjectServers, deleteProject, deployProjectRelease, importProject, listCompanies, listDiscoveredProjects, listProjectReleaseDeployments, listProjectServers, listProjects, listServers, updateProjectServers } from '../api/platform'
import { sessionState } from '../stores/session'
import type { Company, DiscoveredProject, Project, ProjectServer, ProjectServerPoolUpdateRequest, ServerNode } from '../types/api'
import { formatTime, zh } from '../utils/dictionaries'

const route = useRoute()
const companies = ref<Company[]>([])
const projects = ref<Project[]>([])
const discoveredProjects = ref<DiscoveredProject[]>([])
const projectServers = ref<ProjectServer[]>([])
const deploymentHistory = ref<Array<Record<string, unknown>>>([])
const allServers = ref<ServerNode[]>([])
const selectedProject = ref<Project | null>(null)
const selectedDiscovered = ref<DiscoveredProject | null>(null)
const selectedCompanyId = ref<number | undefined>(undefined)
const importCompanyId = ref<number | undefined>(undefined)
const importVisible = ref(false)
const serverPoolVisible = ref(false)
const serverPoolDraft = ref<Array<ProjectServer & { enabled: boolean }>>([])
const serverPoolReason = ref('')
const poolAnalysis = ref<Record<string, unknown> | null>(null)
const importForm = reactive({ remark: '', dispatchMode: 'LOAD_BALANCE' })
const currentCompanyName = computed(() => companies.value.find((item) => item.companyId === sessionState.user?.companyId)?.companyName || '归属公司')
const lastRouteIntent = ref('')

function applyRouteIntent() {
  const key = `${route.query.companyId || ''}:${route.query.openImport || ''}`
  if (lastRouteIntent.value === key) return
  lastRouteIntent.value = key
  const qCompany = Number(route.query.companyId || 0) || undefined
  if (qCompany && qCompany !== selectedCompanyId.value) {
    selectedCompanyId.value = qCompany
    importCompanyId.value = qCompany
    void loadProjects()
  }
  if (route.query.openImport === '1') openImport()
}

async function loadCompanies() { companies.value = await listCompanies(); const qCompany = Number(route.query.companyId || 0) || undefined; if (qCompany) { selectedCompanyId.value = qCompany; importCompanyId.value = qCompany } if (!selectedCompanyId.value && sessionState.user?.isSuperAdmin) selectedCompanyId.value = companies.value[0]?.companyId; if (!importCompanyId.value) importCompanyId.value = selectedCompanyId.value || sessionState.user?.companyId || undefined }
async function loadProjects() { projects.value = await listProjects(sessionState.user?.isSuperAdmin ? selectedCompanyId.value : sessionState.user?.companyId || undefined) }
async function loadAll() { await loadCompanies(); await loadProjects() }
function openImport() { importVisible.value = true; selectedDiscovered.value = null; if (!sessionState.user?.isSuperAdmin) importCompanyId.value = sessionState.user?.companyId || undefined; void loadDiscovered() }
async function loadDiscovered() { discoveredProjects.value = await listDiscoveredProjects(importCompanyId.value) }
function setDiscovered(row: DiscoveredProject) { if (row.selectable) selectedDiscovered.value = row }
function discoveredRowClass({ row }: { row: DiscoveredProject }) { return row.selectable ? '' : 'disabled-row' }
async function submitImport() { if (!selectedDiscovered.value) return; await importProject({ discoveredProjectId: selectedDiscovered.value.discoveredProjectId, remark: importForm.remark, dispatchMode: importForm.dispatchMode }); ElMessage.success('项目已接入'); importVisible.value = false; await loadAll() }
async function selectProject(row: Project) { selectedProject.value = row; await refreshSelectedProject() }
async function refreshSelectedProject() { await loadProjectServers(); await loadProjectDeployments() }
async function loadProjectServers() { if (selectedProject.value) projectServers.value = await listProjectServers(selectedProject.value.projectId) }
async function loadProjectDeployments() { if (selectedProject.value) deploymentHistory.value = await listProjectReleaseDeployments(selectedProject.value.projectId) }
async function deleteProjectRow(row: Project) {
  try {
    await ElMessageBox.confirm(`确认删除项目“${row.projectName}”？删除后会向项目执行节点下发容器清理指令；存在历史运行记录的项目会归档隐藏。`, '删除项目确认', { type: 'warning' })
    const result = await deleteProject(row.projectId)
    const cleanupCount = result.containerCleanupCommands?.length || 0
    ElMessage.success(result.deleted ? `项目已删除，已下发 ${cleanupCount} 条容器清理指令` : `项目已有历史运行记录，已归档隐藏，并下发 ${cleanupCount} 条容器清理指令`)
    if (selectedProject.value?.projectId === row.projectId) {
      selectedProject.value = null
      projectServers.value = []
      deploymentHistory.value = []
    }
    await loadProjects()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(error instanceof Error ? error.message : '删除项目失败')
  }
}
async function openServerPoolEditor() {
  if (!selectedProject.value) return
  allServers.value = await listServers(selectedProject.value.companyId)
  const current = new Map(projectServers.value.map((item) => [item.serverId, item]))
  serverPoolDraft.value = allServers.value.map((server, index) => {
    const existing = current.get(server.serverId)
    if (existing) return { ...existing, enabled: ['ENABLED', 'RECOVERING'].includes(existing.schedulingStatus) }
    return {
      projectServerId: 0,
      companyId: server.companyId,
      projectId: selectedProject.value!.projectId,
      serverId: server.serverId,
      serverName: server.serverName,
      serverCode: server.serverCode,
      deploymentStatus: 'NOT_DEPLOYED',
      schedulingStatus: 'ENABLED',
      imageReadinessStatus: 'OUTDATED',
      serverRole: selectedProject.value!.dispatchMode === 'PRIMARY_STANDBY' ? (index === 0 ? 'PRIMARY' : 'STANDBY') : 'ACTIVE',
      priority: 100 + index,
      weight: 100,
      maxConcurrency: Math.max(1, Math.min(4, server.maxContainerSlots || 4)),
      autoEjectEnabled: true,
      autoRecoverEnabled: true,
      latestImageDigest: selectedProject.value!.latestImageDigest || '',
      lastDeployedAt: null,
      disabledReason: '保存后由 执行时按 版本凭据 拉取镜像',
      manageStatus: server.manageStatus,
      healthStatus: server.healthStatus,
      capacityStatus: server.capacityStatus,
      enabled: false,
    }
  })
  poolAnalysis.value = null
  serverPoolVisible.value = true
}
function poolPayload(): ProjectServerPoolUpdateRequest {
  return {
    reason: serverPoolReason.value,
    servers: serverPoolDraft.value
      .filter((item) => item.enabled || item.projectServerId)
      .map((item) => ({
        serverId: item.serverId,
        schedulingStatus: item.enabled ? item.schedulingStatus : 'PAUSED',
        serverRole: item.serverRole,
        priority: item.priority,
        weight: item.weight,
        maxConcurrency: item.maxConcurrency,
        autoEjectEnabled: item.autoEjectEnabled,
        autoRecoverEnabled: item.autoRecoverEnabled,
      })),
  }
}
async function analyzePool() { if (!selectedProject.value) return; poolAnalysis.value = await analyzeProjectServers(selectedProject.value.projectId, poolPayload()) }



async function deploySelectedRelease() {
  if (!selectedProject.value) return
  const serverIds = serverPoolDraft.value.filter((item) => item.enabled).map((item) => item.serverId)
  const result = await deployProjectRelease(selectedProject.value.projectId, { serverIds, reason: serverPoolReason.value || '项目部署中心手动部署' })
  ElMessage.success(result.message || '部署单已创建')
  await refreshSelectedProject()
  await loadProjects()
}

async function oneClickDeploy(row: Project | null) {
  if (!row) return
  try {
    await ElMessageBox.confirm(`确认部署当前版本项目“${row.projectName}”？平台会自动选择可用执行节点，下发镜像拉取、目录准备和运行时自检指令。`, '部署当前版本确认', { type: 'warning' })
    const result = await deployProjectRelease(row.projectId, { serverIds: [], autoSelect: true, reason: '项目部署当前版本' })
    ElMessage.success(result.message || '部署当前版本单已创建')
    selectedProject.value = row
    await refreshSelectedProject()
    await loadProjects()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(error instanceof Error ? error.message : '部署当前版本失败')
  }
}

function deploymentStepText(row: Record<string, unknown>) {
  const strategy = row.strategy as Record<string, unknown> | undefined
  const steps = Array.isArray(strategy?.steps) ? strategy.steps as Array<Record<string, unknown>> : []
  const active = steps.find((item) => item.status === 'RUNNING' || item.status === 'FAILED') || steps[steps.length - 1]
  return active ? `${active.name || active.key}：${zh(String(active.status || ''))}` : '-'
}

async function savePool() { if (!selectedProject.value) return; await updateProjectServers(selectedProject.value.projectId, poolPayload()); ElMessage.success('执行节点范围已更新'); serverPoolVisible.value = false; await loadProjectServers(); await loadProjects() }
onMounted(async () => { await loadAll(); applyRouteIntent() })
onActivated(applyRouteIntent)
</script>
<style scoped>
.section-title { display: flex; justify-content: space-between; align-items: center; }
.analysis-box { background: #111827; color: #e5e7eb; padding: 12px; border-radius: 6px; max-height: 260px; overflow: auto; }
.cicd-guide { display: grid; gap: 10px; }
:deep(.disabled-row) { color: #999; background: #f5f7fa; }
</style>

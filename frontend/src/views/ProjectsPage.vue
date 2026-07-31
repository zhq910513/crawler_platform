<template>
  <div class="page-card">
    <div class="toolbar">
      <el-select v-if="sessionState.user?.isSuperAdmin" v-model="selectedCompanyId" placeholder="选择公司" clearable style="width: 220px" @change="loadAll">
        <el-option v-for="company in companies" :key="company.companyId" :label="company.companyName" :value="company.companyId" />
      </el-select>
      <span v-else class="muted">当前公司：{{ currentCompanyName }}</span>
      <el-button v-if="sessionState.user?.isSuperAdmin" type="primary" @click="openImport">接入项目</el-button>
      <el-button @click="loadAll">刷新</el-button>
    </div>

    <el-table :data="projects" border @row-click="selectProject">
      <el-table-column label="项目名称" prop="projectName" min-width="150" />
      <el-table-column label="项目编码" prop="projectCode" min-width="120" />
      <el-table-column label="备注" prop="remark" min-width="160" />
      <el-table-column label="上线状态"><template #default="s">{{ zh(s.row.onlineStatus) }}</template></el-table-column>
      <el-table-column label="最新版本" prop="latestVersion" />
      <el-table-column label="部署服务器数" prop="deployedServerCount" />
      <el-table-column label="启用执行服务器数" prop="executionServerCount" />
      <el-table-column label="调度模式"><template #default="s">{{ zh(s.row.dispatchMode) }}</template></el-table-column>
      <el-table-column label="创建时间"><template #default="s">{{ formatTime(s.row.createdAt) }}</template></el-table-column>
    </el-table>

    <el-divider />
    <section v-if="selectedProject">
      <div class="section-title">
        <h3>部署与执行服务器：{{ selectedProject.projectName }}</h3>
        <div><el-button size="small" @click="openServerPoolEditor">配置执行服务器</el-button><el-button size="small" @click="loadProjectServers">刷新</el-button></div>
      </div>
      <el-table :data="projectServers" border>
        <el-table-column label="服务器名称" prop="serverName" />
        <el-table-column label="服务器编码" prop="serverCode" />
        <el-table-column label="部署状态"><template #default="s">{{ zh(s.row.deploymentStatus) }}</template></el-table-column>
        <el-table-column label="调度状态"><template #default="s">{{ zh(s.row.schedulingStatus) }}</template></el-table-column>
        <el-table-column label="镜像状态"><template #default="s">{{ zh(s.row.imageReadinessStatus) }}</template></el-table-column>
        <el-table-column label="角色"><template #default="s">{{ zh(s.row.serverRole) }}</template></el-table-column>
        <el-table-column label="健康"><template #default="s">{{ zh(s.row.healthStatus || '') }}</template></el-table-column>
        <el-table-column label="容量"><template #default="s">{{ zh(s.row.capacityStatus || '') }}</template></el-table-column>
        <el-table-column label="权重" prop="weight" />
        <el-table-column label="项目并发" prop="maxConcurrency" />
        <el-table-column label="暂停原因" prop="disabledReason" min-width="180" />
      </el-table>
    </section>

    <el-dialog v-model="importVisible" title="接入项目" width="900px">
      <div class="toolbar">
        <el-select v-model="importCompanyId" placeholder="选择公司" style="width: 260px" @change="loadDiscovered">
          <el-option v-for="company in companies" :key="company.companyId" :label="company.companyName" :value="company.companyId" />
        </el-select>
        <el-button @click="loadDiscovered">查询待接入项目</el-button>
      </div>
      <el-table :data="discoveredProjects" border :row-class-name="discoveredRowClass" @row-click="setDiscovered">
        <el-table-column label="项目名称" prop="projectName" />
        <el-table-column label="项目编码" prop="projectCode" />
        <el-table-column label="最新版本" prop="latestVersion" />
        <el-table-column label="部署服务器数" prop="deploymentServerCount" />
        <el-table-column label="状态"><template #default="s">{{ s.row.selectable ? '待接入' : zh(s.row.discoveryStatus) }}</template></el-table-column>
        <el-table-column label="最近部署"><template #default="s">{{ formatTime(s.row.lastDeployedAt) }}</template></el-table-column>
      </el-table>
      <el-form label-position="top" style="margin-top: 14px">
        <el-form-item label="备注"><el-input v-model="importForm.remark" /></el-form-item>
        <el-form-item label="调度模式"><el-select v-model="importForm.dispatchMode"><el-option label="负载均衡" value="LOAD_BALANCE" /><el-option label="主备模式" value="PRIMARY_STANDBY" /></el-select></el-form-item>
      </el-form>
      <template #footer><el-button @click="importVisible = false">取消</el-button><el-button type="primary" :disabled="!selectedDiscovered?.selectable" @click="submitImport">确认接入</el-button></template>
    </el-dialog>

    <el-dialog v-model="serverPoolVisible" title="配置执行服务器" width="980px">
      <p class="muted">只能调整已经部署过该项目的服务器。保存前会进行影响分析，异常服务器不会被强制加入执行池。</p>
      <el-table :data="serverPoolDraft" border>
        <el-table-column label="启用" width="70"><template #default="s"><el-checkbox v-model="s.row.enabled" /></template></el-table-column>
        <el-table-column label="服务器" min-width="160"><template #default="s">{{ s.row.serverName }} / {{ s.row.serverCode }}</template></el-table-column>
        <el-table-column label="调度状态" width="140"><template #default="s"><el-select v-model="s.row.schedulingStatus"><el-option label="可调度" value="ENABLED" /><el-option label="排空中" value="DRAINING" /><el-option label="人工暂停" value="PAUSED" /><el-option label="禁用" value="DISABLED" /></el-select></template></el-table-column>
        <el-table-column label="角色" width="140"><template #default="s"><el-select v-model="s.row.serverRole"><el-option label="活动节点" value="ACTIVE" /><el-option label="主服务器" value="PRIMARY" /><el-option label="备用服务器" value="STANDBY" /><el-option label="候选节点" value="CANDIDATE" /></el-select></template></el-table-column>
        <el-table-column label="优先级" width="120"><template #default="s"><el-input-number v-model="s.row.priority" :min="1" /></template></el-table-column>
        <el-table-column label="权重" width="120"><template #default="s"><el-input-number v-model="s.row.weight" :min="0" /></template></el-table-column>
        <el-table-column label="项目并发" width="130"><template #default="s"><el-input-number v-model="s.row.maxConcurrency" :min="1" /></template></el-table-column>
      </el-table>
      <el-form label-position="top" style="margin-top: 14px"><el-form-item label="调整原因"><el-input v-model="serverPoolReason" /></el-form-item></el-form>
      <pre v-if="poolAnalysis" class="analysis-box">{{ JSON.stringify(poolAnalysis, null, 2) }}</pre>
      <template #footer><el-button @click="serverPoolVisible = false">取消</el-button><el-button @click="analyzePool">影响分析</el-button><el-button type="primary" @click="savePool">保存</el-button></template>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { analyzeProjectServers, importProject, listCompanies, listDiscoveredProjects, listProjectServers, listProjects, updateProjectServers } from '../api/platform'
import { sessionState } from '../stores/session'
import type { Company, DiscoveredProject, Project, ProjectServer, ProjectServerPoolUpdateRequest } from '../types/api'
import { formatTime, zh } from '../utils/dictionaries'

const companies = ref<Company[]>([])
const projects = ref<Project[]>([])
const discoveredProjects = ref<DiscoveredProject[]>([])
const projectServers = ref<ProjectServer[]>([])
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

async function loadCompanies() { companies.value = await listCompanies(); if (!selectedCompanyId.value && sessionState.user?.isSuperAdmin) selectedCompanyId.value = companies.value[0]?.companyId; if (!importCompanyId.value) importCompanyId.value = selectedCompanyId.value || sessionState.user?.companyId || undefined }
async function loadProjects() { projects.value = await listProjects(sessionState.user?.isSuperAdmin ? selectedCompanyId.value : sessionState.user?.companyId || undefined) }
async function loadAll() { await loadCompanies(); await loadProjects() }
function openImport() { importVisible.value = true; selectedDiscovered.value = null; void loadDiscovered() }
async function loadDiscovered() { discoveredProjects.value = await listDiscoveredProjects(importCompanyId.value) }
function setDiscovered(row: DiscoveredProject) { if (row.selectable) selectedDiscovered.value = row }
function discoveredRowClass({ row }: { row: DiscoveredProject }) { return row.selectable ? '' : 'disabled-row' }
async function submitImport() { if (!selectedDiscovered.value) return; await importProject({ discoveredProjectId: selectedDiscovered.value.discoveredProjectId, remark: importForm.remark, dispatchMode: importForm.dispatchMode }); ElMessage.success('项目已接入'); importVisible.value = false; await loadAll() }
async function selectProject(row: Project) { selectedProject.value = row; await loadProjectServers() }
async function loadProjectServers() { if (selectedProject.value) projectServers.value = await listProjectServers(selectedProject.value.projectId) }
function openServerPoolEditor() { serverPoolDraft.value = projectServers.value.map((item) => ({ ...item, enabled: ['ENABLED', 'RECOVERING'].includes(item.schedulingStatus) })); poolAnalysis.value = null; serverPoolVisible.value = true }
function poolPayload(): ProjectServerPoolUpdateRequest { return { reason: serverPoolReason.value, servers: serverPoolDraft.value.map((item) => ({ serverId: item.serverId, schedulingStatus: item.enabled ? item.schedulingStatus : 'PAUSED', serverRole: item.serverRole, priority: item.priority, weight: item.weight, maxConcurrency: item.maxConcurrency, autoEjectEnabled: item.autoEjectEnabled, autoRecoverEnabled: item.autoRecoverEnabled })) } }
async function analyzePool() { if (!selectedProject.value) return; poolAnalysis.value = await analyzeProjectServers(selectedProject.value.projectId, poolPayload()) }
async function savePool() { if (!selectedProject.value) return; await updateProjectServers(selectedProject.value.projectId, poolPayload()); ElMessage.success('执行服务器池已更新'); serverPoolVisible.value = false; await loadProjectServers(); await loadProjects() }
onMounted(loadAll)
</script>
<style scoped>
.section-title { display: flex; justify-content: space-between; align-items: center; }
.analysis-box { background: #111827; color: #e5e7eb; padding: 12px; border-radius: 6px; max-height: 260px; overflow: auto; }
:deep(.disabled-row) { color: #999; background: #f5f7fa; }
</style>

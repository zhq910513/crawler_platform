<template>
  <div class="page-card resources-page">
    <div class="toolbar resource-toolbar">
      <div>
        <h3>数据资源配置</h3>
        <p class="muted">按公司维护数据库、缓存和对象存储资源。同一家公司可以配置多种类型，也可以配置多个同类型资源；备注用于说明这个资源具体做什么。</p>
      </div>
      <div class="toolbar-actions">
        <el-select v-if="sessionState.user?.isSuperAdmin" v-model="filters.companyId" filterable placeholder="选择公司" style="width: 240px" @change="load">
          <el-option v-for="company in companies" :key="company.companyId" :label="company.companyName" :value="company.companyId" />
        </el-select>
        <el-button type="primary" @click="openCreateDialog">新增数据资源</el-button>
        <el-button @click="load">刷新</el-button>
      </div>
    </div>

    <div class="filter-panel">
      <el-select v-model="filters.resourceCategory" clearable placeholder="资源大类" @change="load">
        <el-option v-for="item in categoryOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-select v-model="filters.resourceEngine" clearable placeholder="具体类型" @change="load">
        <el-option v-for="item in allEngineOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-select v-model="filters.resourceRole" clearable placeholder="资源用途" @change="load">
        <el-option v-for="item in roleOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-select v-model="filters.testStatus" clearable placeholder="测试状态" @change="load">
        <el-option v-for="item in testStatusOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-input v-model="filters.keyword" clearable placeholder="搜索名称 / 编码 / 备注" @keyup.enter="load" @clear="load" />
      <el-button @click="load">查询</el-button>
    </div>

    <el-empty v-if="!rows.length" description="还没有数据资源">
      <div class="empty-hint">请先为公司新增数据资源，例如采集结果库、账号缓存、原始数据存储或媒体文件存储。</div>
      <el-button type="primary" @click="openCreateDialog">新增数据资源</el-button>
    </el-empty>

    <div v-else class="resource-grid">
      <div v-for="item in rows" :key="item.configId" class="resource-card">
        <div class="resource-card-head">
          <div>
            <div class="resource-name">{{ item.resourceName }}</div>
            <div class="resource-code">编码：{{ item.resourceCode }}</div>
          </div>
          <div class="tag-stack">
            <el-tag :type="item.enabled ? 'success' : 'info'" effect="light">{{ item.enabled ? '启用' : '停用' }}</el-tag>
            <el-tag :type="statusTag(item.testStatus)" effect="light">{{ testText(item.testStatus) }}</el-tag>
          </div>
        </div>
        <div class="resource-meta">
          <span>{{ item.categoryLabel }} / {{ item.engineLabel }}</span>
          <span>用途：{{ item.roleLabel }}</span>
          <span>连接：{{ item.connectionSummary || '-' }}</span>
        </div>
        <div class="resource-remark">备注：{{ item.remark || '-' }}</div>
        <div class="resource-config">
          <div v-for="(value, key) in item.configSummary" :key="key" class="resource-kv"><span>{{ key }}</span><strong>{{ value || '-' }}</strong></div>
        </div>
        <div class="resource-foot">
          <span class="muted">{{ item.lastTestMessage || '尚未校验' }}</span>
          <div class="resource-actions">
            <el-button size="small" @click="openEditDialog(item)">编辑</el-button>
            <el-button size="small" type="primary" @click="testItem(item.configId)">基础校验</el-button>
            <el-button size="small" @click="toggleStatus(item)">{{ item.enabled ? '停用' : '启用' }}</el-button>
          </div>
        </div>
      </div>
    </div>

    <el-dialog v-model="dialogVisible" title="配置数据资源" width="760px">
      <el-form label-position="top">
        <el-row :gutter="14">
          <el-col :span="12"><el-form-item label="资源名称"><el-input v-model="form.resourceName" placeholder="例如：百度爱采购结果库" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="资源编码"><el-input v-model="form.resourceCode" placeholder="baidu_aicaigou_result_mysql" /></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="备注 / 用途说明"><el-input v-model="form.remark" type="textarea" :rows="2" placeholder="说明这个数据库具体做什么，避免误选、误写、误删。" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="资源大类"><el-select v-model="form.resourceCategory" class="full-width" @change="onCategoryChange"><el-option v-for="item in categoryOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="具体类型"><el-select v-model="form.resourceEngine" class="full-width" @change="onEngineChange"><el-option v-for="item in engineOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="资源用途"><el-select v-model="form.resourceRole" class="full-width"><el-option v-for="item in roleOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="连接方式"><el-select v-model="form.connectionMode" class="full-width" @change="applyTemplate"><el-option v-for="item in modeOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="启用状态"><el-switch v-model="form.enabled" active-text="启用" inactive-text="停用" /></el-form-item></el-col>
        </el-row>

        <el-divider content-position="left">连接配置</el-divider>
        <el-row :gutter="14">
          <el-col v-for="field in fields" :key="field.key" :span="field.span || 12">
            <el-form-item :label="field.label">
              <el-input v-if="field.type !== 'select' && field.type !== 'switch'" v-model="form.config[field.key]" :type="field.secret ? 'password' : 'text'" show-password />
              <el-select v-else-if="field.type === 'select'" v-model="form.config[field.key]" class="full-width">
                <el-option v-for="option in field.options || []" :key="option.value" :label="option.label" :value="option.value" />
              </el-select>
              <el-switch v-else v-model="form.config[field.key]" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save">保存配置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listCompanies, listCompanyResourceConfigs, saveCompanyResourceConfig, testCompanyResourceConfig, updateCompanyResourceStatus } from '../api/platform'
import { sessionState } from '../stores/session'
import type { Company, CompanyResourceConfig } from '../types/api'

type Option = { label: string; value: string }
type FieldDef = { key: string; label: string; secret?: boolean; span?: number; type?: 'select' | 'switch'; default?: string | number | boolean; options?: Option[] }

const route = useRoute()
const companies = ref<Company[]>([])
const rows = ref<CompanyResourceConfig[]>([])
const dialogVisible = ref(false)
const filters = reactive<{ companyId: number; resourceCategory: string; resourceEngine: string; resourceRole: string; testStatus: string; keyword: string }>({
  companyId: Number(route.query.companyId || 0),
  resourceCategory: '',
  resourceEngine: '',
  resourceRole: '',
  testStatus: '',
  keyword: '',
})
const form = reactive<{ resourceId?: number; resourceName: string; resourceCode: string; resourceCategory: string; resourceEngine: string; resourceRole: string; connectionMode: string; remark: string; enabled: boolean; config: Record<string, string | number | boolean> }>({
  resourceName: '',
  resourceCode: '',
  resourceCategory: 'RELATIONAL_DB',
  resourceEngine: 'MYSQL',
  resourceRole: 'RESULT_DB',
  connectionMode: 'HOST_PORT',
  remark: '',
  enabled: true,
  config: {},
})

const categoryOptions: Option[] = [
  { label: '关系型数据库', value: 'RELATIONAL_DB' },
  { label: '文档数据库', value: 'DOCUMENT_DB' },
  { label: '缓存数据库', value: 'CACHE_DB' },
  { label: '对象存储', value: 'OBJECT_STORAGE' },
]
const engineByCategory: Record<string, Option[]> = {
  RELATIONAL_DB: [{ label: 'MySQL', value: 'MYSQL' }, { label: 'PostgreSQL', value: 'POSTGRESQL' }, { label: 'SQL Server', value: 'SQLSERVER' }],
  DOCUMENT_DB: [{ label: 'MongoDB', value: 'MONGODB' }],
  CACHE_DB: [{ label: 'Redis', value: 'REDIS' }],
  OBJECT_STORAGE: [{ label: '阿里云 OSS', value: 'ALIYUN_OSS' }, { label: 'S3', value: 'S3' }, { label: 'MinIO', value: 'MINIO' }],
}
const allEngineOptions = Object.values(engineByCategory).flat()
const roleOptions: Option[] = [
  { label: '主业务数据库', value: 'MAIN_DB' },
  { label: '采集结果库', value: 'RESULT_DB' },
  { label: '客户源数据库', value: 'SOURCE_DB' },
  { label: '原始数据存储', value: 'RAW_STORAGE' },
  { label: '账号/账号缓存', value: 'COOKIE_CACHE' },
  { label: '任务状态缓存', value: 'TASK_STATE_CACHE' },
  { label: '媒体文件存储', value: 'MEDIA_STORAGE' },
  { label: '临时中转存储', value: 'TEMP_STORAGE' },
  { label: '分析统计库', value: 'ANALYTICS_DB' },
  { label: '日志存储', value: 'LOG_STORAGE' },
  { label: '其他', value: 'OTHER' },
]
const modeOptions = computed<Option[]>(() => {
  if (form.resourceEngine === 'MONGODB') return [{ label: 'URI 连接串', value: 'URI' }, { label: '主机端口', value: 'HOST_PORT' }]
  if (['ALIYUN_OSS', 'S3'].includes(form.resourceEngine)) return [{ label: '云服务', value: 'CLOUD_SERVICE' }]
  if (form.resourceEngine === 'MINIO') return [{ label: '主机端口', value: 'HOST_PORT' }, { label: '云服务', value: 'CLOUD_SERVICE' }]
  return [{ label: '主机端口', value: 'HOST_PORT' }]
})
const engineOptions = computed(() => engineByCategory[form.resourceCategory] || [])
const templates: Record<string, FieldDef[]> = {
  MYSQL: [{ key: 'host', label: '地址' }, { key: 'port', label: '端口', default: 3306 }, { key: 'database', label: '数据库名' }, { key: 'username', label: '用户名' }, { key: 'password', label: '密码', secret: true, span: 24 }, { key: 'charset', label: '字符集', default: 'utf8mb4' }, { key: 'sslMode', label: 'SSL 模式', type: 'select', default: 'DISABLED', options: [{ label: 'DISABLED', value: 'DISABLED' }, { label: 'PREFERRED', value: 'PREFERRED' }, { label: 'REQUIRED', value: 'REQUIRED' }] }],
  POSTGRESQL: [{ key: 'host', label: '地址' }, { key: 'port', label: '端口', default: 5432 }, { key: 'database', label: '数据库名' }, { key: 'schema', label: 'Schema', default: 'public' }, { key: 'username', label: '用户名' }, { key: 'password', label: '密码', secret: true, span: 24 }, { key: 'sslMode', label: 'SSL 模式', type: 'select', default: 'prefer', options: [{ label: 'disable', value: 'disable' }, { label: 'prefer', value: 'prefer' }, { label: 'require', value: 'require' }] }],
  SQLSERVER: [{ key: 'host', label: '地址' }, { key: 'port', label: '端口', default: 1433 }, { key: 'database', label: '数据库名' }, { key: 'username', label: '用户名' }, { key: 'password', label: '密码', secret: true, span: 24 }, { key: 'encrypt', label: 'Encrypt', type: 'switch', default: false }, { key: 'trustServerCertificate', label: '信任服务器证书', type: 'switch', default: true }],
  MONGODB_URI: [{ key: 'uri', label: '连接串', secret: true, span: 24 }, { key: 'database', label: '数据库名' }, { key: 'authSource', label: '认证库', default: 'admin' }],
  MONGODB_HOST_PORT: [{ key: 'host', label: '地址' }, { key: 'port', label: '端口', default: 27017 }, { key: 'database', label: '数据库名' }, { key: 'username', label: '用户名' }, { key: 'password', label: '密码', secret: true, span: 24 }, { key: 'authSource', label: '认证库', default: 'admin' }],
  REDIS: [{ key: 'host', label: '地址' }, { key: 'port', label: '端口', default: 6379 }, { key: 'database', label: '库编号', default: 0 }, { key: 'username', label: '用户名' }, { key: 'password', label: '密码', secret: true, span: 24 }, { key: 'tls', label: 'TLS', type: 'switch', default: false }],
  ALIYUN_OSS: [{ key: 'endpoint', label: 'Endpoint' }, { key: 'bucket', label: 'Bucket' }, { key: 'region', label: 'Region' }, { key: 'accessKeyId', label: 'AccessKey ID', secret: true }, { key: 'accessKeySecret', label: 'AccessKey Secret', secret: true }, { key: 'secure', label: 'HTTPS', type: 'switch', default: true }],
  S3: [{ key: 'endpoint', label: 'Endpoint' }, { key: 'bucket', label: 'Bucket' }, { key: 'region', label: 'Region' }, { key: 'accessKeyId', label: 'AccessKey ID', secret: true }, { key: 'accessKeySecret', label: 'AccessKey Secret', secret: true }, { key: 'pathStyleAccess', label: 'Path Style', type: 'switch', default: false }],
  MINIO: [{ key: 'endpoint', label: 'Endpoint' }, { key: 'bucket', label: 'Bucket' }, { key: 'region', label: 'Region' }, { key: 'accessKeyId', label: 'AccessKey ID', secret: true }, { key: 'accessKeySecret', label: 'AccessKey Secret', secret: true }, { key: 'pathStyleAccess', label: 'Path Style', type: 'switch', default: true }],
}
const fields = computed(() => templates[templateKey()] || [])

function templateKey() { return form.resourceEngine === 'MONGODB' ? `MONGODB_${form.connectionMode}` : form.resourceEngine }
function applyTemplate(preserve = false) {
  const old = preserve ? { ...form.config } : {}
  const next: Record<string, string | number | boolean> = {}
  for (const field of fields.value) next[field.key] = old[field.key] ?? field.default ?? ''
  form.config = next
}
function onCategoryChange() { form.resourceEngine = engineOptions.value[0]?.value || ''; onEngineChange() }
function onEngineChange() { form.connectionMode = modeOptions.value[0]?.value || 'HOST_PORT'; applyTemplate() }
function defaultCode() { return `${form.resourceRole.toLowerCase()}_${form.resourceEngine.toLowerCase()}` }
function openCreateDialog() {
  Object.assign(form, { resourceId: undefined, resourceName: '', resourceCode: '', resourceCategory: 'RELATIONAL_DB', resourceEngine: 'MYSQL', resourceRole: 'RESULT_DB', connectionMode: 'HOST_PORT', remark: '', enabled: true, config: {} })
  applyTemplate()
  dialogVisible.value = true
}
function openEditDialog(item: CompanyResourceConfig) {
  Object.assign(form, { resourceId: item.resourceId, resourceName: item.resourceName, resourceCode: item.resourceCode, resourceCategory: item.resourceCategory, resourceEngine: item.resourceEngine, resourceRole: item.resourceRole, connectionMode: item.connectionMode, remark: item.remark, enabled: item.enabled, config: { ...item.configMasked } })
  applyTemplate(true)
  dialogVisible.value = true
}
function testText(status: string) { return ({ NOT_TESTED: '未测试', CONFIG_INVALID: '配置不完整', CONFIG_VALID: '配置完整', CONNECTION_FAILED: '连接失败', CONNECTION_PASSED: '连接通过', MANUAL_CONFIRMED: '人工确认' } as Record<string, string>)[status] || status }
function statusTag(status: string) { if (['CONFIG_VALID', 'CONNECTION_PASSED', 'MANUAL_CONFIRMED'].includes(status)) return 'success'; if (['CONFIG_INVALID', 'CONNECTION_FAILED'].includes(status)) return 'danger'; return 'warning' }
async function loadCompaniesData() { companies.value = await listCompanies(); if (!filters.companyId) filters.companyId = sessionState.user?.companyId || companies.value[0]?.companyId || 0 }
async function load() { await loadCompaniesData(); if (!filters.companyId) return; rows.value = await listCompanyResourceConfigs({ companyId: filters.companyId, resourceCategory: filters.resourceCategory || undefined, resourceEngine: filters.resourceEngine || undefined, resourceRole: filters.resourceRole || undefined, testStatus: filters.testStatus || undefined, keyword: filters.keyword || undefined }) }
async function save() {
  if (!form.resourceCode) form.resourceCode = defaultCode()
  await saveCompanyResourceConfig({ resourceId: form.resourceId, companyId: filters.companyId, projectId: null, resourceName: form.resourceName, resourceCode: form.resourceCode, resourceCategory: form.resourceCategory, resourceEngine: form.resourceEngine, resourceRole: form.resourceRole, connectionMode: form.connectionMode, remark: form.remark, enabled: form.enabled, config: form.config })
  ElMessage.success('数据资源已保存')
  dialogVisible.value = false
  await load()
}
async function testItem(configId: number) { const result = await testCompanyResourceConfig(configId); ElMessage.success(result.lastTestMessage || '基础校验完成'); await load() }
async function toggleStatus(item: CompanyResourceConfig) { await updateCompanyResourceStatus(item.configId, !item.enabled); ElMessage.success(item.enabled ? '数据资源已停用' : '数据资源已启用'); await load() }
onMounted(load)
</script>

<style scoped>
.resource-toolbar { align-items: flex-start; justify-content: space-between; }
.resource-toolbar h3 { margin: 0 0 6px; }
.toolbar-actions { display: flex; gap: 10px; align-items: center; }
.filter-panel { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)) auto; gap: 10px; margin: 14px 0 18px; }
.empty-hint { margin-bottom: 12px; color: #64748b; }
.resource-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.resource-card { padding: 16px; border: 1px solid #e7edf5; border-radius: 16px; background: linear-gradient(180deg, #fff, #f8fbff); }
.resource-card-head, .resource-foot { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.resource-name { color: #111827; font-weight: 800; font-size: 16px; }
.resource-code { color: #94a3b8; font-size: 12px; margin-top: 2px; }
.tag-stack { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
.resource-meta { margin-top: 12px; display: grid; gap: 4px; color: #475569; font-size: 13px; }
.resource-remark { margin-top: 10px; color: #64748b; font-size: 13px; line-height: 1.5; }
.resource-config { margin: 12px 0; padding: 10px 12px; border-radius: 12px; background: #f8fafc; }
.resource-kv { display: flex; justify-content: space-between; gap: 12px; padding: 4px 0; color: #64748b; font-size: 12px; }
.resource-kv strong { color: #334155; font-weight: 600; word-break: break-all; }
.resource-actions { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.full-width { width: 100%; }
@media (max-width: 1180px) { .filter-panel { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 980px) { .resource-grid { grid-template-columns: 1fr; } }
</style>

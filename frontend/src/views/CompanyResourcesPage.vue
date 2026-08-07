<template>
  <div class="page-card resources-page">
    <div class="toolbar resource-toolbar">
      <div>
        <h3>数据库配置</h3>
        <p class="muted">配置公司运行所需的数据库、缓存和存储资源。敏感信息只保存，不在列表中明文展示。</p>
      </div>
      <div class="toolbar-actions">
        <el-select v-if="sessionState.user?.isSuperAdmin" v-model="selectedCompanyId" filterable placeholder="选择公司" style="width: 240px" @change="load">
          <el-option v-for="company in companies" :key="company.companyId" :label="company.companyName" :value="company.companyId" />
        </el-select>
        <el-button type="primary" @click="openDialog()">新增配置</el-button>
        <el-button @click="load">刷新</el-button>
      </div>
    </div>

    <el-empty v-if="!rows.length" description="还没有数据库配置">
      <div class="empty-hint">请先配置公司主业务数据库，任务运行后会将数据写入这里。</div>
      <el-button type="primary" @click="openDialog('MYSQL_MAIN')">配置主业务数据库</el-button>
    </el-empty>

    <div v-else class="resource-grid">
      <div v-for="item in rows" :key="item.configId" class="resource-card">
        <div class="resource-card-head">
          <div>
            <div class="resource-name">{{ item.resourceName || item.resourceLabel }}</div>
            <div class="muted">{{ item.resourceLabel }}</div>
          </div>
          <el-tag :type="statusTag(item.testStatus)" effect="light">{{ testText(item.testStatus) }}</el-tag>
        </div>
        <div class="resource-config">
          <div v-for="(value, key) in item.configMasked" :key="key" class="resource-kv"><span>{{ key }}</span><strong>{{ value || '-' }}</strong></div>
        </div>
        <div class="resource-foot">
          <span class="muted">{{ item.lastTestMessage || '尚未测试' }}</span>
          <div><el-button size="small" @click="openDialog(item.resourceType)">编辑</el-button><el-button size="small" type="primary" @click="testItem(item.configId)">测试</el-button></div>
        </div>
      </div>
    </div>

    <el-dialog v-model="dialogVisible" title="配置数据库资源" width="620px">
      <el-form label-position="top">
        <el-form-item label="资源类型">
          <el-select v-model="form.resourceType" class="full-width" @change="applyTemplate">
            <el-option label="主业务数据库" value="MYSQL_MAIN" />
            <el-option label="登录缓存库" value="REDIS_CACHE" />
            <el-option label="原始数据存储" value="MONGO_RAW" />
            <el-option label="媒体存储" value="OSS_MEDIA" />
          </el-select>
        </el-form-item>
        <el-form-item label="配置名称"><el-input v-model="form.resourceName" /></el-form-item>
        <el-row :gutter="14">
          <el-col v-for="field in fields" :key="field.key" :span="field.span || 12">
            <el-form-item :label="field.label">
              <el-input v-model="form.config[field.key]" :type="field.secret ? 'password' : 'text'" show-password />
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
import { listCompanies, listCompanyResourceConfigs, saveCompanyResourceConfig, testCompanyResourceConfig } from '../api/platform'
import { sessionState } from '../stores/session'
import type { Company, CompanyResourceConfig } from '../types/api'

const route = useRoute()
const companies = ref<Company[]>([])
const selectedCompanyId = ref<number>(Number(route.query.companyId || 0))
const rows = ref<CompanyResourceConfig[]>([])
const dialogVisible = ref(false)
const form = reactive<{ resourceType: string; resourceName: string; config: Record<string, string> }>({ resourceType: 'MYSQL_MAIN', resourceName: '主业务数据库', config: {} })
const templates: Record<string, Array<{ key: string; label: string; secret?: boolean; span?: number }>> = {
  MYSQL_MAIN: [{ key: 'host', label: '地址' }, { key: 'port', label: '端口' }, { key: 'database', label: '数据库名' }, { key: 'username', label: '用户名' }, { key: 'password', label: '密码', secret: true, span: 24 }],
  REDIS_CACHE: [{ key: 'host', label: '地址' }, { key: 'port', label: '端口' }, { key: 'database', label: '库编号' }, { key: 'password', label: '密码', secret: true }],
  MONGO_RAW: [{ key: 'uri', label: '连接地址', secret: true, span: 24 }, { key: 'database', label: '数据库名' }],
  OSS_MEDIA: [{ key: 'endpoint', label: '访问地址' }, { key: 'bucket', label: 'Bucket' }, { key: 'accessKeyId', label: 'AccessKey ID', secret: true }, { key: 'accessKeySecret', label: 'AccessKey Secret', secret: true }],
}
const fields = computed(() => templates[form.resourceType] || [])
function labelOf(type: string) { return ({ MYSQL_MAIN: '主业务数据库', REDIS_CACHE: '登录缓存库', MONGO_RAW: '原始数据存储', OSS_MEDIA: '媒体存储' } as Record<string, string>)[type] || '资源配置' }
function applyTemplate() { form.resourceName = labelOf(form.resourceType); form.config = {} }
function openDialog(type = 'MYSQL_MAIN') { form.resourceType = type; applyTemplate(); dialogVisible.value = true }
function testText(status: string) { return ({ PASSED: '测试通过', FAILED: '测试失败', NOT_TESTED: '未测试' } as Record<string, string>)[status] || status }
function statusTag(status: string) { if (status === 'PASSED') return 'success'; if (status === 'FAILED') return 'danger'; return 'warning' }
async function loadCompaniesData() { companies.value = await listCompanies(); if (!selectedCompanyId.value) selectedCompanyId.value = sessionState.user?.companyId || companies.value[0]?.companyId || 0 }
async function load() { await loadCompaniesData(); if (selectedCompanyId.value) rows.value = await listCompanyResourceConfigs(selectedCompanyId.value) }
async function save() { await saveCompanyResourceConfig({ companyId: selectedCompanyId.value, resourceType: form.resourceType, resourceName: form.resourceName, config: form.config }); ElMessage.success('配置已保存'); dialogVisible.value = false; await load() }
async function testItem(configId: number) { const result = await testCompanyResourceConfig(configId); ElMessage.success(result.lastTestMessage || '测试完成'); await load() }
onMounted(load)
</script>

<style scoped>
.resource-toolbar { align-items: flex-start; justify-content: space-between; }
.resource-toolbar h3 { margin: 0 0 6px; }
.toolbar-actions { display: flex; gap: 10px; align-items: center; }
.empty-hint { margin-bottom: 12px; color: #64748b; }
.resource-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.resource-card { padding: 16px; border: 1px solid #e7edf5; border-radius: 16px; background: linear-gradient(180deg, #fff, #f8fbff); }
.resource-card-head, .resource-foot { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.resource-name { color: #111827; font-weight: 800; font-size: 16px; }
.resource-config { margin: 12px 0; padding: 10px 12px; border-radius: 12px; background: #f8fafc; }
.resource-kv { display: flex; justify-content: space-between; gap: 12px; padding: 4px 0; color: #64748b; font-size: 12px; }
.resource-kv strong { color: #334155; font-weight: 600; }
@media (max-width: 980px) { .resource-grid { grid-template-columns: 1fr; } }
</style>

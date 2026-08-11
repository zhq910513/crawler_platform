<template>
  <el-drawer v-model="state.visible" title="配置助手" size="420px" class="config-assistant-drawer" :append-to-body="true">
    <div v-loading="state.loading" class="assistant-body">
      <template v-if="state.status">
        <div class="assistant-hero">
          <div class="assistant-company">{{ state.status.companyName }}</div>
          <div class="assistant-summary">{{ state.status.summary }}</div>
          <div class="assistant-progress-line">
            <span>配置进度：{{ state.status.completedCount }} / {{ state.status.totalCount }}</span>
            <el-progress :percentage="progressPercent" :show-text="false" />
          </div>
          <el-alert v-if="!state.status.platformPublicUrlConfigured" type="warning" show-icon :closable="false" title="请先配置控制端公网回调地址，远程执行节点才能正常接入。" />
        </div>

        <div class="step-list">
          <div v-for="step in state.status.steps" :key="step.key" class="assistant-step" :class="`status-${step.status.toLowerCase()}`">
            <div class="step-icon">{{ stepIcon(step.status) }}</div>
            <div class="step-main">
              <div class="step-title-row">
                <div class="step-title">{{ step.label }}</div>
                <el-tag size="small" :type="tagType(step.status)" effect="light">{{ statusText(step.status) }}</el-tag>
              </div>
              <div class="step-desc">{{ step.description }}</div>
              <div v-if="step.blocked" class="step-block">{{ step.blockReason }}</div>
              <div v-else class="step-action"><el-button size="small" :type="step.status === 'DONE' ? 'default' : 'primary'" @click="goStep(step)">{{ step.actionLabel }}</el-button></div>
            </div>
          </div>
        </div>
      </template>
      <el-empty v-else description="请选择公司后打开配置助手" />
    </div>
    <template #footer>
      <div class="assistant-footer">
        <el-button @click="state.visible = false">稍后配置</el-button>
        <el-button type="primary" :loading="state.loading" @click="refreshConfigAssistant">刷新状态</el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { configAssistantState as state, refreshConfigAssistant } from '../stores/configAssistant'
import type { CompanySetupStep } from '../types/api'

const router = useRouter()
const progressPercent = computed(() => state.status ? Math.round((state.status.completedCount / Math.max(1, state.status.totalCount)) * 100) : 0)
function statusText(status: string) { return ({ DONE: '已完成', MISSING: '未配置', ACTION: '待处理', RISK: '有风险', BLOCKED: '暂不可用' } as Record<string, string>)[status] || status }
function tagType(status: string) { if (status === 'DONE') return 'success'; if (status === 'RISK') return 'warning'; if (status === 'BLOCKED') return 'info'; return 'primary' }
function stepIcon(status: string) { if (status === 'DONE') return '✓'; if (status === 'RISK') return '!'; if (status === 'BLOCKED') return '○'; return '•' }
async function goStep(step: CompanySetupStep) {
  const query: Record<string, string> = { companyId: String(state.companyId) }
  if (step.key === 'agent') query.openOnboarding = '1'
  if (step.key === 'platform_url') query.focus = 'platformUrl'
  if (step.key === 'project') query.openImport = '1'
  await router.push({ path: step.route, query })
}
</script>

<style scoped>
.assistant-body { min-height: 520px; }
.assistant-hero { padding: 14px; border: 1px solid #e0ecff; border-radius: 16px; background: linear-gradient(180deg, #f8fbff, #eef6ff); margin-bottom: 14px; }
.assistant-company { color: #0f172a; font-size: 18px; font-weight: 800; }
.assistant-summary { margin-top: 5px; color: #64748b; font-size: 13px; }
.assistant-progress-line { margin: 12px 0; color: #475569; font-size: 12px; }
.step-list { display: flex; flex-direction: column; gap: 10px; }
.assistant-step { display: flex; gap: 12px; padding: 13px; border: 1px solid #e7edf5; border-radius: 14px; background: #fff; }
.assistant-step.status-done { background: #f8fffb; border-color: #dcfce7; }
.assistant-step.status-risk { background: #fffaf0; border-color: #fde68a; }
.assistant-step.status-blocked { background: #f8fafc; }
.step-icon { display: flex; align-items: center; justify-content: center; width: 26px; height: 26px; border-radius: 50%; background: #e0ecff; color: #2563eb; font-weight: 800; flex: none; }
.status-done .step-icon { background: #dcfce7; color: #16a34a; }
.status-risk .step-icon { background: #fef3c7; color: #d97706; }
.status-blocked .step-icon { background: #e5e7eb; color: #64748b; }
.step-main { min-width: 0; flex: 1; }
.step-title-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.step-title { color: #111827; font-weight: 800; }
.step-desc { margin-top: 6px; color: #64748b; font-size: 12px; line-height: 1.5; }
.step-block { margin-top: 8px; color: #9ca3af; font-size: 12px; }
.step-action { margin-top: 10px; }
.assistant-footer { display: flex; justify-content: flex-end; gap: 10px; }
</style>

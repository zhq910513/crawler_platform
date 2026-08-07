import { reactive } from 'vue'
import { getCompanySetupStatus } from '../api/platform'
import type { CompanySetupStatus } from '../types/api'

export const configAssistantState = reactive({
  visible: false,
  loading: false,
  companyId: 0,
  companyName: '',
  status: null as CompanySetupStatus | null,
})

export async function openConfigAssistant(companyId: number, companyName = '') {
  configAssistantState.companyId = companyId
  configAssistantState.companyName = companyName
  configAssistantState.visible = true
  await refreshConfigAssistant()
}

export async function refreshConfigAssistant() {
  if (!configAssistantState.companyId) return
  configAssistantState.loading = true
  try {
    configAssistantState.status = await getCompanySetupStatus(configAssistantState.companyId)
    configAssistantState.companyName = configAssistantState.status.companyName || configAssistantState.companyName
  } finally {
    configAssistantState.loading = false
  }
}

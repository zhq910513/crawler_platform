import { computed, reactive } from 'vue'
import api from './api'

export const platformContext = reactive({
  companies: [],
  projects: [],
  companyId: Number(localStorage.getItem('crawler_company_id')) || null,
  projectId: Number(localStorage.getItem('crawler_project_id')) || null,
  loaded: false
})

export const currentCompany = computed(() => platformContext.companies.find(x => x.company_id === platformContext.companyId) || null)
export const currentProject = computed(() => platformContext.projects.find(x => x.project_id === platformContext.projectId) || null)
export const projectRole = computed(() => currentProject.value?.role || null)
export const canOperateProject = computed(() => ['OWNER', 'OPERATOR'].includes(projectRole.value))
export const canManageProject = computed(() => projectRole.value === 'OWNER')

export async function loadPlatformContext() {
  const companies = (await api.get('/companies')).data
  platformContext.companies = companies
  if (!companies.some(x => x.company_id === platformContext.companyId)) platformContext.companyId = companies[0]?.company_id || null
  const projects = (await api.get('/projects', { params: platformContext.companyId ? { company_id: platformContext.companyId } : {} })).data
  platformContext.projects = projects
  if (!projects.some(x => x.project_id === platformContext.projectId)) platformContext.projectId = projects[0]?.project_id || null
  persistContext()
  platformContext.loaded = true
}

export async function selectCompany(companyId) {
  platformContext.companyId = companyId || null
  const projects = (await api.get('/projects', { params: companyId ? { company_id: companyId } : {} })).data
  platformContext.projects = projects
  platformContext.projectId = projects[0]?.project_id || null
  persistContext()
}

export function selectProject(projectId) {
  platformContext.projectId = projectId || null
  persistContext()
}

function persistContext() {
  if (platformContext.companyId) localStorage.setItem('crawler_company_id', String(platformContext.companyId)); else localStorage.removeItem('crawler_company_id')
  if (platformContext.projectId) localStorage.setItem('crawler_project_id', String(platformContext.projectId)); else localStorage.removeItem('crawler_project_id')
}

export function clearPlatformContext() {
  Object.assign(platformContext, { companies: [], projects: [], companyId: null, projectId: null, loaded: false })
  localStorage.removeItem('crawler_company_id')
  localStorage.removeItem('crawler_project_id')
}

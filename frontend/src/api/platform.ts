import { http, request } from './client'
import type { AgentJoinTokenCreateRequest, AgentJoinTokenResult, AgentRegistrationRequest, Company, DashboardSummary, DiscoveredProject, AlertEvent, NotificationChannel, NotificationChannelCreateRequest, Project, ProjectImportRequest, ProjectReleaseDeploymentResult, ProjectReleaseDeployRequest, ProjectServer, ProjectServerPoolUpdateRequest, ProjectUpdateRequest, RunRecord, ServerCreateRequest, ServerNode, Task, TaskCreateRequest, TaskDefinition, TaskUpdateRequest, UserAccount, UserCreateRequest, ScheduleUpdateRequest, CronPreviewRequest, CronPreviewResult, OwnPasswordUpdateRequest, UserPasswordResetRequest, AccountCredential, AccountStatusEvent, AccountStatusEventCreateRequest, RunDiagnosis, RunEvent, RunLogTail, CredentialSubjectBinding, CredentialSubjectBindingCreateRequest, CredentialSubjectBindingUpdateRequest, CredentialLease, SystemSettings, CompanyResourceConfig, CompanySetupStatus } from '../types/api'

export function listCompanies() { return request<Company[]>(http.get('/companies')) }
export function createCompany(payload: { companyCode: string; companyName: string; timezone?: string; description?: string }) { return request<Company>(http.post('/companies', payload)) }
export function createDiscoveryToken(companyId: number) { return request<{ tokenId: number; discoveryToken: string }>(http.post(`/companies/${companyId}/discovery-tokens`)) }

export function getSystemSettings() { return request<SystemSettings>(http.get('/system-settings')) }
export function updateSystemSettings(payload: { platformPublicUrl?: string }) { return request<SystemSettings>(http.patch('/system-settings', payload)) }
export function getCompanySetupStatus(companyId: number) { return request<CompanySetupStatus>(http.get(`/companies/${companyId}/setup-status`)) }
export function listCompanyResourceConfigs(companyId?: number) { return request<CompanyResourceConfig[]>(http.get('/company-resource-configs', { params: { companyId } })) }
export function saveCompanyResourceConfig(payload: { companyId: number; resourceType: string; resourceName?: string; config: Record<string, unknown> }) { return request<CompanyResourceConfig>(http.post('/company-resource-configs', payload)) }
export function testCompanyResourceConfig(configId: number, forceSuccess = false) { return request<CompanyResourceConfig>(http.post(`/company-resource-configs/${configId}/tests`, { forceSuccess })) }

export function listUsers() { return request<UserAccount[]>(http.get('/users')) }
export function createUser(payload: UserCreateRequest) { return request<UserAccount>(http.post('/users', payload)) }
export function revokeUserSession(userId: number, reason: string) { return request<{ revokedCount: number }>(http.post(`/users/${userId}/session-revocations`, { reason })) }
export function changeOwnPassword(payload: OwnPasswordUpdateRequest) { return request<{ revokedCount: number; reloginRequired: boolean }>(http.patch('/users/me/password', payload)) }
export function resetUserPassword(userId: number, payload: UserPasswordResetRequest) { return request<{ userId: number; revokedCount: number; mustChangePassword: boolean }>(http.post(`/users/${userId}/password-resets`, payload)) }

export function listServers(companyId?: number) { return request<ServerNode[]>(http.get('/servers', { params: { companyId } })) }
export function createServer(payload: ServerCreateRequest) { return request<ServerNode>(http.post('/servers', payload)) }
export function registerAgent(payload: AgentRegistrationRequest) { return request<{ agentToken: string }>(http.post('/agents', payload)) }

export function createAgentJoinToken(payload: AgentJoinTokenCreateRequest) { return request<AgentJoinTokenResult>(http.post('/servers/agent-join-tokens', payload)) }
export function listAgentJoinTokens(companyId?: number) { return request<Record<string, unknown>[]>(http.get('/servers/agent-join-tokens', { params: { companyId } })) }

export function listDiscoveredProjects(companyId?: number) { return request<DiscoveredProject[]>(http.get('/discovered-projects', { params: { companyId } })) }
export function listProjects(companyId?: number) { return request<Project[]>(http.get('/projects', { params: { companyId } })) }
export function importProject(payload: ProjectImportRequest) { return request<Project>(http.post('/projects', payload)) }
export function updateProject(projectId: number, payload: ProjectUpdateRequest) { return request<Project>(http.patch(`/projects/${projectId}`, payload)) }
export function listProjectServers(projectId: number) { return request<ProjectServer[]>(http.get(`/projects/${projectId}/servers`)) }
export function analyzeProjectServers(projectId: number, payload: ProjectServerPoolUpdateRequest) { return request<Record<string, unknown>>(http.post(`/projects/${projectId}/server-pool-analyses`, payload)) }
export function updateProjectServers(projectId: number, payload: ProjectServerPoolUpdateRequest) { return request<ProjectServer[]>(http.put(`/projects/${projectId}/servers`, payload)) }

export function deployProjectRelease(projectId: number, payload: ProjectReleaseDeployRequest) { return request<ProjectReleaseDeploymentResult>(http.post(`/projects/${projectId}/release-deployments`, payload)) }
export function listProjectReleaseDeployments(projectId: number) { return request<Record<string, unknown>[]>(http.get(`/projects/${projectId}/release-deployments`)) }
export function listTaskDefinitions(projectId: number) { return request<TaskDefinition[]>(http.get(`/projects/${projectId}/task-definitions`)) }

export function listTasks(params?: { companyId?: number; projectId?: number }) { return request<Task[]>(http.get('/tasks', { params })) }
export function createTask(payload: TaskCreateRequest) { return request<Task>(http.post('/tasks', payload)) }
export function updateTask(taskId: number, payload: TaskUpdateRequest) { return request<Task>(http.patch(`/tasks/${taskId}`, payload)) }
export function deleteTask(taskId: number) { return request<{ taskId: number; deleted: boolean; archived: boolean; runCount: number }>(http.delete(`/tasks/${taskId}`)) }
export function updateTaskSchedule(taskId: number, payload: ScheduleUpdateRequest) { return request<Record<string, unknown>>(http.patch(`/tasks/${taskId}/schedules`, payload)) }
export function previewCronExpression(payload: CronPreviewRequest) { return request<CronPreviewResult>(http.post('/cron-previews', payload)) }
export function createRun(taskId: number, parameters: Record<string, unknown> = {}) { return request<RunRecord>(http.post('/runs', { taskId, parameters })) }
export function listRuns(params?: { companyId?: number; projectId?: number; taskId?: number }) { return request<RunRecord[]>(http.get('/runs', { params })) }
export function listRunEvents(runId: number) { return request<RunEvent[]>(http.get(`/runs/${runId}/events`)) }
export function getRunLogTail(runId: number, params?: { afterSeq?: number; limit?: number; keyword?: string; stream?: string }) { return request<RunLogTail>(http.get(`/runs/${runId}/log-tails`, { params })) }
export function getRunDiagnosis(runId: number) { return request<RunDiagnosis>(http.get(`/runs/${runId}/diagnoses`)) }
export function downloadRunLogs(runId: number) { return request<{ filename: string; content: string; logTruncated: boolean; logBytes: number }>(http.get(`/runs/${runId}/log-downloads`)) }


export function listAccountCredentials(params?: { companyId?: number; platformCode?: string; credentialKey?: string }) { return request<AccountCredential[]>(http.get('/account-credentials', { params })) }
export function listAccountStatusEvents(credentialId: number, limit = 100) { return request<AccountStatusEvent[]>(http.get(`/account-credentials/${credentialId}/status-events`, { params: { limit } })) }
export function setAccountCredentialEnabled(credentialId: number, enabled: boolean, reason = '') { return request<AccountCredential>(http.patch(`/account-credentials/${credentialId}/enabled`, { enabled, reason })) }
export function createAccountStatusEvent(payload: AccountStatusEventCreateRequest) { return request<AccountStatusEvent>(http.post('/account-status-events', payload)) }
export function listCredentialSubjectBindings(params?: { companyId?: number; platformCode?: string; subjectType?: string; credentialKey?: string }) { return request<CredentialSubjectBinding[]>(http.get('/credential-subject-bindings', { params })) }
export function listCredentialLeases(params?: { companyId?: number; platformCode?: string; credentialKey?: string }) { return request<CredentialLease[]>(http.get('/credential-leases', { params })) }
export function createCredentialSubjectBinding(payload: CredentialSubjectBindingCreateRequest) { return request<CredentialSubjectBinding>(http.post('/credential-subject-bindings', payload)) }
export function updateCredentialSubjectBinding(bindingId: number, payload: CredentialSubjectBindingUpdateRequest) { return request<CredentialSubjectBinding>(http.patch(`/credential-subject-bindings/${bindingId}`, payload)) }

export function listNotificationChannels() { return request<NotificationChannel[]>(http.get('/notification-channels')) }
export function createNotificationChannel(payload: NotificationChannelCreateRequest) { return request<NotificationChannel>(http.post('/notification-channels', payload)) }
export function testNotificationChannel(channelId: number, title: string, content: string) { return request<{ success: boolean; message: string }>(http.post(`/notification-channels/${channelId}/tests`, { title, content })) }
export function listDashboardSummaries() { return request<DashboardSummary>(http.get('/dashboard-summaries')) }

export function listAlertEvents() { return request<AlertEvent[]>(http.get('/alerts')) }
export function acknowledgeAlert(alertId: number) { return request<AlertEvent>(http.patch(`/alerts/${alertId}/acknowledgements`)) }
export function resolveAlert(alertId: number) { return request<AlertEvent>(http.patch(`/alerts/${alertId}/resolutions`)) }

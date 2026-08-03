import { http, request } from './client'
import type { AgentRegistrationRequest, Company, DashboardSummary, DiscoveredProject, AlertEvent, NotificationChannel, NotificationChannelCreateRequest, Project, ProjectImportRequest, ProjectServer, ProjectServerPoolUpdateRequest, ProjectUpdateRequest, RunRecord, ServerCreateRequest, ServerNode, Task, TaskCreateRequest, TaskDefinition, TaskUpdateRequest, UserAccount, UserCreateRequest, ScheduleUpdateRequest, CronPreviewRequest, CronPreviewResult, OwnPasswordUpdateRequest, UserPasswordResetRequest, RunDiagnosis, RunEvent, RunLogTail } from '../types/api'

export function listCompanies() { return request<Company[]>(http.get('/companies')) }
export function createCompany(payload: { companyCode: string; companyName: string; timezone?: string; description?: string }) { return request<Company>(http.post('/companies', payload)) }
export function createDiscoveryToken(companyId: number) { return request<{ tokenId: number; discoveryToken: string }>(http.post(`/companies/${companyId}/discovery-tokens`)) }

export function listUsers() { return request<UserAccount[]>(http.get('/users')) }
export function createUser(payload: UserCreateRequest) { return request<UserAccount>(http.post('/users', payload)) }
export function revokeUserSession(userId: number, reason: string) { return request<{ revokedCount: number }>(http.post(`/users/${userId}/session-revocations`, { reason })) }
export function changeOwnPassword(payload: OwnPasswordUpdateRequest) { return request<{ revokedCount: number; reloginRequired: boolean }>(http.patch('/users/me/password', payload)) }
export function resetUserPassword(userId: number, payload: UserPasswordResetRequest) { return request<{ userId: number; revokedCount: number; mustChangePassword: boolean }>(http.post(`/users/${userId}/password-resets`, payload)) }

export function listServers(companyId?: number) { return request<ServerNode[]>(http.get('/servers', { params: { companyId } })) }
export function createServer(payload: ServerCreateRequest) { return request<ServerNode>(http.post('/servers', payload)) }
export function registerAgent(payload: AgentRegistrationRequest) { return request<{ agentToken: string }>(http.post('/agents', payload)) }

export function listDiscoveredProjects(companyId?: number) { return request<DiscoveredProject[]>(http.get('/discovered-projects', { params: { companyId } })) }
export function listProjects(companyId?: number) { return request<Project[]>(http.get('/projects', { params: { companyId } })) }
export function importProject(payload: ProjectImportRequest) { return request<Project>(http.post('/projects', payload)) }
export function updateProject(projectId: number, payload: ProjectUpdateRequest) { return request<Project>(http.patch(`/projects/${projectId}`, payload)) }
export function listProjectServers(projectId: number) { return request<ProjectServer[]>(http.get(`/projects/${projectId}/servers`)) }
export function analyzeProjectServers(projectId: number, payload: ProjectServerPoolUpdateRequest) { return request<Record<string, unknown>>(http.post(`/projects/${projectId}/server-pool-analyses`, payload)) }
export function updateProjectServers(projectId: number, payload: ProjectServerPoolUpdateRequest) { return request<ProjectServer[]>(http.put(`/projects/${projectId}/servers`, payload)) }
export function listTaskDefinitions(projectId: number) { return request<TaskDefinition[]>(http.get(`/projects/${projectId}/task-definitions`)) }

export function listTasks(params?: { companyId?: number; projectId?: number }) { return request<Task[]>(http.get('/tasks', { params })) }
export function createTask(payload: TaskCreateRequest) { return request<Task>(http.post('/tasks', payload)) }
export function updateTask(taskId: number, payload: TaskUpdateRequest) { return request<Task>(http.patch(`/tasks/${taskId}`, payload)) }
export function updateTaskSchedule(taskId: number, payload: ScheduleUpdateRequest) { return request<Record<string, unknown>>(http.patch(`/tasks/${taskId}/schedules`, payload)) }
export function previewCronExpression(payload: CronPreviewRequest) { return request<CronPreviewResult>(http.post('/cron-previews', payload)) }
export function createRun(taskId: number, parameters: Record<string, unknown> = {}) { return request<RunRecord>(http.post('/runs', { taskId, parameters })) }
export function listRuns(params?: { companyId?: number; projectId?: number; taskId?: number }) { return request<RunRecord[]>(http.get('/runs', { params })) }
export function listRunEvents(runId: number) { return request<RunEvent[]>(http.get(`/runs/${runId}/events`)) }
export function getRunLogTail(runId: number, params?: { afterSeq?: number; limit?: number; keyword?: string; stream?: string }) { return request<RunLogTail>(http.get(`/runs/${runId}/log-tails`, { params })) }
export function getRunDiagnosis(runId: number) { return request<RunDiagnosis>(http.get(`/runs/${runId}/diagnoses`)) }
export function downloadRunLogs(runId: number) { return request<{ filename: string; content: string; logTruncated: boolean; logBytes: number }>(http.get(`/runs/${runId}/log-downloads`)) }

export function listNotificationChannels() { return request<NotificationChannel[]>(http.get('/notification-channels')) }
export function createNotificationChannel(payload: NotificationChannelCreateRequest) { return request<NotificationChannel>(http.post('/notification-channels', payload)) }
export function testNotificationChannel(channelId: number, title: string, content: string) { return request<{ success: boolean; message: string }>(http.post(`/notification-channels/${channelId}/tests`, { title, content })) }
export function listDashboardSummaries() { return request<DashboardSummary>(http.get('/dashboard-summaries')) }

export function listAlertEvents() { return request<AlertEvent[]>(http.get('/alerts')) }
export function acknowledgeAlert(alertId: number) { return request<AlertEvent>(http.patch(`/alerts/${alertId}/acknowledgements`)) }
export function resolveAlert(alertId: number) { return request<AlertEvent>(http.patch(`/alerts/${alertId}/resolutions`)) }


export interface SystemVersionInfo {
  appName: string
  version: string
  gitCommit: string
  buildTime: string
}

export interface BackendHealthData extends SystemVersionInfo {
  status: string
  migrationVersion: string
}

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export interface UserInfo {
  userId: number
  companyId: number | null
  userName: string
  nickName: string
  roleType: 'SUPER_ADMIN' | 'NORMAL_USER'
  status: string
  isSuperAdmin: boolean
  passwordChangeRequired?: boolean
  passwordUpdatedAt?: string | null
}

export interface LoginRequest {
  userName: string
  password: string
  forceLoginToken?: string | null
}

export interface LoginConflictData {
  lastActiveAt: string
  deviceName: string
  loginIp: string
  forceLoginToken: string
}

export interface LoginResponse {
  accessToken: string
  tokenType: string
  sessionId: string
  passwordChangeRequired?: boolean
  user: UserInfo
}

export interface Company {
  companyId: number
  companyCode: string
  companyName: string
  status: string
  timezone: string
  description: string
  createdAt: string
}

export interface UserAccount {
  userId: number
  companyId: number | null
  userName: string
  nickName: string
  roleType: string
  status: string
  lastLoginAt?: string
  mustChangePassword?: boolean
  passwordUpdatedAt?: string | null
}


export interface AgentMetrics {
  dockerStatus?: string
  cpuUsage?: number | null
  memoryUsage?: number | null
  diskUsage?: number | null
  inodeUsage?: number | null
  loadAverage?: number | null
  runningContainers?: number
  availableSlots?: number
  maxSlots?: number
  currentRuns?: number[]
  projectDataRootWritable?: boolean | null
  dockerSockAccessible?: boolean | null
  timezone?: string
  lastError?: string
  lastHeartbeatAt?: string
}

export interface ServerNode {
  serverId: number
  companyId: number
  serverCode: string
  serverName: string
  serverIp: string
  environment: string
  maxContainerSlots: number
  manageStatus: string
  healthStatus: string
  capacityStatus: string
  metrics: AgentMetrics
  labels?: Record<string, unknown>
  capabilities?: Record<string, unknown>
  registryCredentialRef?: string
  workDir?: string
  description: string
}

export interface DiscoveredProject {
  discoveredProjectId: number
  companyId: number
  projectKey: string
  projectCode: string
  projectName: string
  imageRepository: string
  latestVersion: string
  latestImageDigest: string
  discoveryStatus: string
  parseStatus: string
  parseError: string
  formalProjectId: number | null
  lastDeployedAt: string | null
  deploymentServerCount?: number
  selectable?: boolean
}

export interface Project {
  projectId: number
  companyId: number
  projectCode: string
  projectName: string
  projectKey: string
  remark: string
  repositoryUrl: string
  imageRepository: string
  status: string
  onlineStatus: string
  dispatchMode: string
  minAvailableServers: number
  maxActiveServers: number
  allowDeployedFallback: boolean
  allowCompanyPoolFallback: boolean
  defaultRuntimeMode?: string
  defaultTaskMaxConcurrency?: number
  defaultGroupMaxConcurrency?: number
  defaultShmSizeMb?: number
  defaultLogLimitMb?: number
  containerConfig?: Record<string, unknown>
  latestVersion?: string
  latestImageDigest?: string
  deployedServerCount?: number
  executionServerCount?: number
  createdAt: string
}

export interface ProjectServer {
  projectServerId: number
  companyId: number
  projectId: number
  serverId: number
  deploymentStatus: string
  schedulingStatus: string
  imageReadinessStatus: string
  serverRole: string
  priority: number
  weight: number
  maxConcurrency: number
  autoEjectEnabled: boolean
  autoRecoverEnabled: boolean
  latestImageDigest: string
  lastDeployedAt: string | null
  disabledReason: string
  serverName?: string
  serverCode?: string
  manageStatus?: string
  healthStatus?: string
  capacityStatus?: string
}

export interface TaskDefinition {
  definitionId: number
  companyId: number
  projectId: number
  definitionKey: string
  taskName: string
  entryModule: string
  entryFunction: string
  defaultParams: Record<string, unknown>
  suggestedCron: string
  executionMode: string
  idempotencyPolicy: string
  runtimeMode?: string
  taskGroup?: string
  taskMaxConcurrency?: number
  groupMaxConcurrency?: number
  exclusiveMode?: boolean
  ioClass?: string
  shmSizeMb?: number
  logLimitMb?: number
  resourceLocks?: string[]
  platformCode?: string
  requiredConfigs?: Array<Record<string, unknown>>
  requiredCredentials?: Array<Record<string, unknown>>
  outputTables?: Array<Record<string, unknown>>
  contractStatus?: string
  contractWarnings?: unknown[]
  definitionStatus: string
  createdAt: string
}

export interface Task {
  taskId: number
  companyId: number
  projectId: number
  definitionId: number | null
  ownerUserId?: number | null
  taskCode: string
  taskName: string
  entryModule: string
  entryFunction: string
  parameters: Record<string, unknown>
  executionMode: string
  idempotencyPolicy: string
  runtimeMode?: string
  taskGroup?: string
  taskMaxConcurrency?: number
  groupMaxConcurrency?: number
  exclusiveMode?: boolean
  ioClass?: string
  shmSizeMb?: number
  logLimitMb?: number
  resourceLocks?: string[]
  status: string
  imagePolicy: string
  releaseChannel: string
  timeoutSeconds: number
  maxRetryCount: number
  description?: string
  scheduleId?: number
  scheduleStatus?: string
  scheduleType?: string
  cronExpression?: string
  scheduleTimezone?: string
  overlapPolicy?: string
  scheduleConfig?: Record<string, unknown>
  scheduleLabel?: string
  nextRunAt?: string | null
  lastTriggeredAt?: string | null
  createdAt: string
}

export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
}

export interface TaskSchedulePanelQuery {
  companyId?: number
  projectId?: number
  taskName?: string
  taskCode?: string
  entryKeyword?: string
  serverId?: number
  taskGroup?: string
  taskPlatform?: string
  taskStatus?: string
  scheduleStatus?: string
  lastRunStatus?: string
  ownerUserId?: number
  page?: number
  pageSize?: number
}

export interface TaskSchedulePanelItem {
  taskId: number
  companyId: number
  companyName: string
  projectId: number
  projectName: string
  taskCode: string
  taskName: string
  taskGroup: string
  taskPlatform: string
  entryModule: string
  entryFunction: string
  entryPath: string
  serverId: number | null
  serverName: string
  serverCode: string
  serverIp: string
  ownerUserId: number | null
  ownerUserName: string
  taskStatus: string
  scheduleId: number | null
  scheduleStatus: string
  scheduleType: string
  cronExpression: string
  scheduleTimezone: string
  overlapPolicy: string
  scheduleConfig: Record<string, unknown>
  scheduleLabel: string
  nextRunAt: string | null
  lastRunId: number | null
  lastRunStatus: string
  routingStatus: string
  lastFinishedAt: string | null
  lastErrorSummary: string
  createdAt: string
  updatedAt: string
}

export interface RunRecord {
  runId: number
  companyId: number
  projectId: number
  taskId: number
  serverId: number | null
  runStatus: string
  routingStatus: string
  routingReason: string
  scheduledAt: string | null
  startedAt: string | null
  finishedAt: string | null
  errorMessage: string
  logStatus?: string
  logBytes?: number
  logLines?: number
  lastLogSeq?: number
  logTruncated?: boolean
  failedStage?: string
  errorType?: string
  errorSummary?: string
  retryable?: boolean | null
  createdAt: string
}

export interface NotificationChannel {
  channelId: number
  scopeType: string
  channelName: string
  channelType: string
  channelStatus: string
  p0Only: boolean
  lastTestAt: string | null
  lastTestResult: string
  cooldownSeconds?: number
}


export interface AlertEvent {
  alertId: number
  companyId: number | null
  projectId: number | null
  severity: string
  alertStatus: string
  alertType: string
  title: string
  content: string
  fingerprint: string
  occurrenceCount: number
  firstSeenAt: string
  lastSeenAt: string
  notifiedAt: string | null
  resolvedAt: string | null
}

export interface DashboardSummary {
  projectCount: number
  serverCount: number
  taskCount: number
  runningCount: number
  waitingCount: number
}

export interface UserCreateRequest { companyId?: number | null; userName: string; nickName: string; password: string; roleType: string; status?: string }
export interface ServerCreateRequest { companyId: number; serverCode: string; serverName: string; serverIp?: string; maxContainerSlots?: number; labels?: Record<string, unknown>; capabilities?: Record<string, unknown>; registryCredentialRef?: string; workDir?: string; description?: string }
export interface AgentRegistrationRequest { companyId: number; serverCode: string; serverName: string; serverIp?: string; agentCode: string; agentName?: string; maxContainerSlots?: number }
export interface ProjectImportRequest { discoveredProjectId: number; remark?: string; dispatchMode?: string; minAvailableServers?: number; maxActiveServers?: number; allowDeployedFallback?: boolean; allowCompanyPoolFallback?: boolean; defaultRuntimeMode?: string; defaultTaskMaxConcurrency?: number; defaultGroupMaxConcurrency?: number; defaultShmSizeMb?: number; defaultLogLimitMb?: number; containerConfig?: Record<string, unknown> }
export interface ProjectUpdateRequest { projectName?: string; remark?: string; status?: string; onlineStatus?: string; dispatchMode?: string; minAvailableServers?: number; maxActiveServers?: number; allowDeployedFallback?: boolean; allowCompanyPoolFallback?: boolean; defaultRuntimeMode?: string; defaultTaskMaxConcurrency?: number; defaultGroupMaxConcurrency?: number; defaultShmSizeMb?: number; defaultLogLimitMb?: number; containerConfig?: Record<string, unknown>; description?: string }
export interface ProjectServerUpsertRequest { serverId: number; schedulingStatus: string; serverRole: string; priority: number; weight: number; maxConcurrency: number; autoEjectEnabled: boolean; autoRecoverEnabled: boolean }
export interface ProjectServerPoolUpdateRequest { servers: ProjectServerUpsertRequest[]; reason?: string }
export interface TaskCreateRequest { definitionId: number; ownerUserId?: number | null; taskCode: string; taskName: string; parameters?: Record<string, unknown>; configBindings?: Record<string, unknown>; credentialBindings?: Record<string, unknown>; status?: string; imagePolicy?: string; releaseChannel?: string; fixedReleaseId?: number | null; cpuLimit?: number; memoryLimitMb?: number; timeoutSeconds?: number; maxRetryCount?: number; scheduleStatus?: string; scheduleType?: string; cronExpression?: string; scheduleTimezone?: string; overlapPolicy?: string; scheduleConfig?: Record<string, unknown>; scheduleLabel?: string; serverIds?: number[]; runtimeMode?: string; taskGroup?: string; taskMaxConcurrency?: number; groupMaxConcurrency?: number; exclusiveMode?: boolean; ioClass?: string; shmSizeMb?: number; logLimitMb?: number; resourceLocks?: string[]; description?: string }
export interface TaskUpdateRequest { ownerUserId?: number | null; taskName?: string; parameters?: Record<string, unknown>; configBindings?: Record<string, unknown>; credentialBindings?: Record<string, unknown>; status?: string; imagePolicy?: string; releaseChannel?: string; fixedReleaseId?: number | null; cpuLimit?: number; memoryLimitMb?: number; timeoutSeconds?: number; maxRetryCount?: number; runtimeMode?: string; taskGroup?: string; taskMaxConcurrency?: number; groupMaxConcurrency?: number; exclusiveMode?: boolean; ioClass?: string; shmSizeMb?: number; logLimitMb?: number; resourceLocks?: string[]; description?: string }
export interface NotificationChannelCreateRequest { scopeType: string; companyId?: number | null; projectId?: number | null; channelName: string; channelType: string; channelStatus: string; config: Record<string, unknown>; p0Only?: boolean; cooldownSeconds?: number }

export interface ScheduleUpdateRequest { scheduleStatus?: string; scheduleType?: string; cronExpression?: string; scheduleTimezone?: string; overlapPolicy?: string; scheduleConfig?: Record<string, unknown>; scheduleLabel?: string }
export interface CronPreviewRequest { cronExpression?: string; scheduleConfig?: Record<string, unknown>; timezone?: string; count?: number }
export interface CronPreviewResult { valid: boolean; cronExpression: string; timezone: string; nextTimes: string[]; scheduleConfig?: Record<string, unknown>; scheduleLabel?: string }

export interface OwnPasswordUpdateRequest { oldPassword: string; newPassword: string; confirmPassword: string }
export interface UserPasswordResetRequest { newPassword: string; mustChangePassword: boolean }
export interface RunEvent { eventId: number; runId: number; eventType: string; eventLevel: string; stage: string; message: string; payloadJson: Record<string, unknown>; createdAt: string }
export interface RunLogChunk { chunkId: number; runId: number; stream: string; seq: number; offsetStart: number; offsetEnd: number; content: string; contentSize: number; createdAt: string }
export interface RunLogTail { runId: number; lastLogSeq: number; logTruncated: boolean; chunks: RunLogChunk[] }
export interface RunDiagnosis { runId: number; failedStage: string; errorType: string; errorSummary: string; retryable: boolean | null; diagnosis: Record<string, unknown>; logStatus: string; logTruncated: boolean; lastLogSeq: number; lastLogAt: string | null }

export interface AgentJoinTokenCreateRequest { companyId: number; serverCode: string; serverName: string; agentCode: string; agentName?: string; maxContainerSlots?: number; workDir?: string; labels?: Record<string, unknown>; capabilities?: Record<string, unknown>; registryCredentialRef?: string; installMode?: string; expiresInHours?: number }
export interface AgentJoinTokenResult { tokenId: number; companyId: number; agentCode: string; serverCode: string; expiresAt: string; joinToken: string; installCommand: string; note: string }
export interface ProjectReleaseDeployRequest { releaseId?: number | null; serverIds: number[]; prewarmWhenIdle?: boolean; maxParallelPulls?: number; reason?: string }
export interface ProjectReleaseDeploymentResult { deploymentId: number; projectId: number; releaseId: number; releaseVersion: string; imageRepository: string; imageDigest: string; targets: Array<Record<string, unknown>>; message: string }

export interface AccountCredential {
  credentialId: number
  companyId: number
  companyCode: string
  platformCode: string
  credentialKey: string
  credentialName: string
  enabled: boolean
  healthStatus: string
  loginStatus: string
  usageStatus: string
  lastStatusCode: string
  lastStatusSource: string
  lastVerifiedAt: string | null
  lastSuccessAt: string | null
  lastFailureAt: string | null
  failureCount: number
  statusFreshUntil: string | null
  lastVerifiedAgentCode: string
  lastRunId: number | null
  lastTaskId: number | null
  lastErrorSummary: string
  statusMetadata?: Record<string, unknown>
  createdAt: string
  updatedAt: string
}

export interface AccountStatusEvent {
  statusEventId: number
  eventUid: string
  companyId: number
  companyCode: string
  platformCode: string
  credentialKey: string
  credentialId: number | null
  runId: number | null
  taskId: number | null
  agentId: number | null
  agentCode: string
  slot: string
  subjectType?: string
  subjectKey?: string
  subjectName?: string
  affectsCredential?: boolean
  eventType: string
  statusCode: string
  severity: string
  source: string
  messageSanitized: string
  observedAt: string
  payloadSanitized: Record<string, unknown>
  createdAt: string
}

export interface AccountStatusEventCreateRequest {
  companyId?: number | null
  companyCode?: string | null
  platformCode: string
  credentialKey: string
  credentialName?: string
  runId?: number | null
  taskId?: number | null
  agentCode?: string
  slot?: string
  subjectType?: string
  subjectKey?: string
  subjectName?: string
  affectsCredential?: boolean
  eventType?: string
  statusCode: string
  severity?: string
  source?: string
  message?: string
  payload?: Record<string, unknown>
  eventUid?: string | null
}


export interface CredentialLease {
  leaseId: number
  companyId: number
  companyCode: string
  platformCode: string
  credentialId: number | null
  credentialKey: string
  slot: string
  runId: number | null
  taskId: number | null
  agentId: number | null
  agentCode: string
  leaseStatus: string
  leaseUntil: string
  heartbeatAt: string | null
  releasedAt: string | null
  releaseReason: string
  metadataJson?: Record<string, unknown>
  createdAt: string
  updatedAt: string
}

export interface CredentialSubjectBinding {
  bindingId: number
  companyId: number
  companyCode: string
  platformCode: string
  subjectType: string
  subjectKey: string
  subjectName: string
  credentialId: number | null
  credentialKey: string
  bindingStatus: string
  bindingPolicy: string
  rebindingPolicy: string
  source: string
  firstSuccessAt: string | null
  lastSuccessAt: string | null
  lastFailureAt: string | null
  failureCount: number
  lastErrorCode: string
  lastErrorSummary: string
  createdAt: string
  updatedAt: string
}

export interface CredentialSubjectBindingCreateRequest {
  companyId?: number | null
  companyCode?: string | null
  platformCode: string
  subjectType: string
  subjectKey: string
  subjectName?: string
  credentialKey: string
  bindingPolicy?: string
  rebindingPolicy?: string
  metadata?: Record<string, unknown>
}

export interface CredentialSubjectBindingUpdateRequest {
  credentialKey?: string
  bindingStatus?: string
  rebindingPolicy?: string
  reason?: string
  metadata?: Record<string, unknown>
}

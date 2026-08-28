
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
  hostname?: string
  hostIp?: string
  publicIp?: string
  reportedAddress?: string
  observedRemoteAddress?: string
  lastError?: string
  lastHeartbeatAt?: string
  decommissionStatus?: string
  decommissionError?: string
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
  desiredState?: string
  desiredAgentVersion?: string
  lifecycleStatus?: string
  lifecycleAction?: string
  lifecycleError?: string
  healthStatus: string
  capacityStatus: string
  metrics: AgentMetrics
  agentCode?: string
  agentName?: string
  agentConnectionStatus?: string
  agentVersion?: string
  agentLastHeartbeatAt?: string | null
  agentLastError?: string
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
  repositoryUrl: string
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
  discoveryStatus: string
  orchestrationStatus: string
  latestReleaseId?: number | null
  firstSeenReleaseId?: number | null
  lastSeenAt?: string | null
  ignoredAt?: string | null
  ignoredBy?: number | null
  ignoreReason?: string
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
  configBindings?: Record<string, unknown>
  credentialBindings?: Record<string, unknown>
  contractSnapshot?: Record<string, unknown>
  runtimeReadiness?: TaskRuntimeReadiness
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

export interface PendingTaskDefinitionItem {
  definitionId: number
  companyId: number
  companyName: string
  projectId: number
  projectName: string
  definitionKey: string
  taskName: string
  entryModule: string
  entryFunction: string
  entryPath: string
  platformCode: string
  taskGroup: string
  suggestedCron: string
  defaultParams?: Record<string, unknown>
  executionMode?: string
  runtimeMode?: string
  taskMaxConcurrency?: number
  groupMaxConcurrency?: number
  exclusiveMode?: boolean
  ioClass?: string
  shmSizeMb?: number
  logLimitMb?: number
  resourceLocks?: string[]
  requiredConfigs: Array<Record<string, unknown>>
  requiredCredentials: Array<Record<string, unknown>>
  contractStatus: string
  contractWarnings: Array<unknown>
  discoveryStatus: string
  orchestrationStatus: string
  firstSeenReleaseId?: number | null
  latestReleaseId?: number | null
  lastSeenAt?: string | null
  ignoredAt?: string | null
  ignoredBy?: number | null
  ignoreReason?: string
  bindingRequired: boolean
  updatedAt: string
}

export interface TaskSchedulePanelResult extends PageResult<TaskSchedulePanelItem> {
  pendingDefinitions: PendingTaskDefinitionItem[]
  pendingDefinitionTotal: number
  ignoredDefinitions: PendingTaskDefinitionItem[]
  ignoredDefinitionTotal: number
}

export interface TaskRuntimeReadiness {
  ready: boolean
  status: 'READY' | 'NEEDS_REVIEW' | 'BLOCKED' | string
  reasons: string[]
  releaseId?: number | null
  releaseVersion?: string
  definitionKey?: string
  definitionChanged?: boolean
  readyServerCount?: number
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
  runtimeReadiness?: TaskRuntimeReadiness
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
  runtimeIssues?: ControlPlanePreflightCheck[]
  platformPreflight?: ControlPlanePreflight
  platformPreflightHistory?: PlatformPreflightSnapshot[]
}



export interface RunningCenterContainer {
  snapshotId: number
  containerId: string
  containerName: string
  imageDigest: string
  containerStatus: string
  exitCode?: number | null
  oomKilled?: boolean | null
  restartCount?: number
  cpuUsage?: number | null
  memoryUsageMb?: number | null
  startedAt?: string | null
  finishedAt?: string | null
  lastLogLine?: string
  observedAt?: string | null
}

export interface RunningCenterServer {
  serverId: number
  serverName: string
  serverCode: string
  serverIp: string
  healthStatus: string
  capacityStatus: string
  dockerStatus: string
  cpuUsage?: number | null
  memoryUsage?: number | null
  diskUsage?: number | null
  availableSlots?: number | null
  maxSlots?: number | null
  lastHeartbeatAt?: string | null
  lastError?: string
}

export interface RunningCenterRun {
  runId: number
  runStatus: string
  routingStatus: string
  routingReason: string
  releaseId?: number | null
  imageDigest?: string
  startedAt?: string | null
  finishedAt?: string | null
  createdAt?: string
  errorSummary?: string
  failedStage?: string
  errorType?: string
  retryable?: boolean | null
}

export interface RunningCenterTask {
  taskId: number
  taskName: string
  taskCode: string
  taskState: string
  taskStateText: string
  stateLevel: string
  advice: string
  primaryAction: string
  scheduleText: string
  latestRun?: RunningCenterRun | null
  container?: RunningCenterContainer | null
  server?: RunningCenterServer | null
  debug?: Record<string, unknown>
}

export interface RunningCenterProject {
  projectId: number
  projectName: string
  projectCode: string
  projectStatus: string
  projectStatusText: string
  projectAdvice: string
  projectAction: string
  singleTaskProject: boolean
  taskCount: number
  runningTaskCount: number
  failedTaskCount: number
  readyTaskCount: number
  recentResultText: string
  latestVersion: string
  deploymentText: string
  tasks: RunningCenterTask[]
}

export interface RunningCenterSummary {
  company: { companyId: number | null; companyName: string }
  overview: { projectCount: number; taskCount: number; runningCount: number; failedCount: number; readyCount: number; onlineServerCount: number; issueServerCount: number }
  layers: string[]
  projects: RunningCenterProject[]
  updatedAt: string
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

export interface AgentJoinTokenCreateRequest { companyId: number; serverCode: string; serverName: string; agentCode: string; agentName?: string; maxContainerSlots?: number; workDir?: string; labels?: Record<string, unknown>; capabilities?: Record<string, unknown>; registryCredentialRef?: string; installMode?: string; installTarget?: 'LOCAL' | 'REMOTE'; controlPlaneUrl?: string; expiresInHours?: number; replaceExistingAgent?: boolean; autoConfigureDockerRegistry?: boolean }
export interface AgentJoinTokenResult { tokenId: number; companyId: number; agentCode: string; serverCode: string; expiresAt: string; invitationStatus?: string; invitationStatusLabel?: string; joinToken?: string; joinTokenMasked?: string; installCommand: string; connectivityCommand?: string; nodeVerificationScript?: string; controlPlaneUrl?: string; installTarget?: string; warnings?: string[]; controlPlanePreflight?: ControlPlanePreflight; note: string }
export interface ProjectReleaseDeployRequest { releaseId?: number | null; serverIds: number[]; autoSelect?: boolean; prewarmWhenIdle?: boolean; maxParallelPulls?: number; reason?: string }

export interface ProjectPublishPipelineRequest { companyId: number; serverIds: number[]; repositoryUrl: string; refName?: string }
export interface ProjectPublishPipelineStep { key: string; title: string; status: 'wait' | 'process' | 'success' | 'error' | string; message: string; blocking?: boolean; data?: Record<string, unknown> }
export interface ProjectPublishPipelineResult { pipelineStatus: string; canContinue: boolean; steps: ProjectPublishPipelineStep[]; blockers: Array<Record<string, unknown>>; target?: Record<string, unknown>; form?: Record<string, unknown>; deployment?: ProjectReleaseDeploymentResult; targets?: Array<Record<string, unknown>>; buildJob?: Record<string, unknown>; message: string }

export interface SpiderProjectCicdGuide {
  provider: string
  mode: string
  controlPlanePublicBaseUrl: string
  controlPlanePublicBaseUrlSource: string
  controlPlanePublicBaseUrlConfigured: boolean
  controlPlanePublicBaseUrlWarnings: string[]
    companyId: number
  companyCode?: string
  globalVariables: Array<Record<string, unknown>>
  globalSecrets: Array<Record<string, unknown>>
  projectDefaults: Array<Record<string, unknown>>
  workflowPath: string
  workflowContent: string
  helperScriptUrl: string
  initScriptUrl: string
  oneLineInitCommand: string
  commitCommand: string
  notes: string[]
}

export interface ProjectReleaseDeploymentResult { deploymentId: number; projectId: number; releaseId: number; releaseVersion: string; imageRepository: string; imageDigest: string; deploymentStatus?: string; steps?: Array<Record<string, unknown>>; targets: Array<Record<string, unknown>>; message: string }

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

export interface ControlPlanePreflightCheck {
  key: string
  label: string
  status: 'PASS' | 'PENDING' | 'WARN' | 'FAIL'
  message: string
  blocking: boolean
  suggestion: string
  action?: string
  verifyCommand?: string
  impact?: string
  route?: string
  actionLabel?: string
  category?: string
  canIgnore?: boolean
  automationType?: string
  handler?: string
  autoActionCommand?: string
  actionEndpoint?: string
  actionButtonLabel?: string
  actionAvailable?: boolean
  actionUnavailableReason?: string
  executionChannel?: string
  manualCommand?: string
  evidenceSource?: string
  evidenceScope?: string
  details?: Record<string, unknown>
}

export interface ControlPlaneRequiredPort {
  name: string
  host: string
  port: number
  protocol: string
  reason: string
  action?: string
  impact?: string
  actionLabel?: string
  verifyCommand?: string
  automationType?: string
  handler?: string
}

export interface ControlPlanePreflight {
  readyForRemoteAgent: boolean
  status: 'PASS' | 'WARN' | 'FAIL'
  summary: string
  blockingCount: number
  warningCount: number
  pendingCount: number
  verifiedCount: number
  securityAdvisoryCount: number
  checks: ControlPlanePreflightCheck[]
  requiredPorts: ControlPlaneRequiredPort[]
  securityAdvisories?: Array<{ key: string; label: string; level: string; message: string; suggestion?: string; action?: string; verifyCommand?: string; scope?: string; details?: Record<string, unknown> }>
  runtimeEvidence?: { registeredAgentCount: number; onlineAgentCount: number; unavailableAgentCount?: number; freshnessSeconds?: number; checkedAt?: string; agents: Array<{ agentId: number; serverId: number; agentCode?: string; connectionStatus?: string; lastHeartbeatAt?: string; agentImage?: string; reportedDigest?: string; actualDigest?: string; dockerStatus?: string; serverHealthStatus?: string; lastError?: string }>; unavailableAgents?: Array<{ agentId: number; serverId: number; agentCode?: string; connectionStatus?: string; lastHeartbeatAt?: string; agentImage?: string; reportedDigest?: string; actualDigest?: string; dockerStatus?: string; serverHealthStatus?: string; lastError?: string }> }
  agentImage: string
  agentImageDigest?: string
  controlPlaneUrl?: string
  changes?: string[]
  latestSnapshot?: PlatformPreflightSnapshot
  checkedAt?: string
  checkSource?: string
  checkSourceLabel?: string
  nextAction?: string
  automationSummary?: { ciCdOrServerScript: number; pageAction: number; platformScript: number; nodeInstallerAuthorized: number; nodeVerify: number; cloudConsole: number; manual: number }
  platformActionEnabled?: boolean
  platformActionAvailable?: boolean
  platformActionCapability?: { enabled: boolean; available: boolean; reason?: string; manualCommand?: string; channel?: string }
  securityGroupChecklist?: {
    title?: string
    summary?: string
    controlPlaneUrl?: string
    rules: Array<{ name: string; protocol: string; port: number; source: string; suggestion: string; risk?: string }>
    notes?: string[]
  }
}

export interface PlatformPreflightSnapshot {
  snapshotId: number
  status: 'PASS' | 'WARN' | 'FAIL' | string
  blockingCount: number
  warningCount: number
  pendingCount?: number
  verifiedCount?: number
  securityAdvisoryCount?: number
  checkSource: string
  checkSourceLabel: string
  controlPlaneUrl: string
  agentImage: string
  agentImageDigest?: string
  summary: string
  changes: string[]
  checkedAt?: string
  createdAt?: string
  triggeredBy?: number | null
}

export interface PlatformActionResult {
  actionKey: string
  status: 'IDLE' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'UNAVAILABLE' | string
  stage?: string
  message?: string
  logs?: string[]
  manualCommand?: string
  startedAt?: string
  finishedAt?: string
  executable?: boolean
  running?: boolean
  triggeredBy?: string
}

export interface SystemSettings {
  controlPlanePublicBaseUrl: string
  controlPlanePublicBaseUrlSource: string
  controlPlanePublicBaseUrlConfigured: boolean
  controlPlanePublicBaseUrlWarnings: string[]
  controlPlanePreflight?: ControlPlanePreflight
}

export interface CompanyResourceConfig {
  configId: number
  resourceId: number
  companyId: number
  projectId?: number | null
  resourceName: string
  resourceCode: string
  resourceCategory: string
  resourceEngine: string
  resourceRole: string
  connectionMode: string
  categoryLabel: string
  engineLabel: string
  roleLabel: string
  resourceLabel: string
  connectionSummary: string
  configSummary: Record<string, unknown>
  configMasked: Record<string, unknown>
  remark: string
  enabled: boolean
  testStatus: string
  lastTestAt: string | null
  lastTestMessage: string
  legacyResourceType?: string | null
  updatedAt: string
}

export interface CompanyResourceConfigPayload {
  resourceId?: number
  companyId: number
  projectId?: number | null
  resourceName: string
  resourceCode: string
  resourceCategory: string
  resourceEngine: string
  resourceRole: string
  connectionMode: string
  remark: string
  enabled: boolean
  config: Record<string, unknown>
}

export interface CompanySetupStep {
  key: string
  label: string
  description: string
  status: 'DONE' | 'MISSING' | 'ACTION' | 'RISK' | 'BLOCKED'
  route: string
  actionLabel: string
  metrics: Record<string, unknown>
  blocked: boolean
  blockReason: string
}

export interface CompanySetupStatus {
  companyId: number
  companyName: string
  companyCode: string
  mode: 'FIRST_SETUP' | 'CONTINUE_SETUP' | 'RECHECK' | 'READY'
  summary: string
  completedCount: number
  totalCount: number
  nextStepKey: string
  nextStepLabel: string
  controlPlanePublicBaseUrl: string
  controlPlanePublicBaseUrlSource: string
  controlPlanePublicBaseUrlConfigured: boolean
  controlPlanePublicBaseUrlWarnings: string[]
    steps: CompanySetupStep[]
  counts: Record<string, number>
}

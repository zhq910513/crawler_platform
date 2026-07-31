export const statusText: Record<string, string> = {
  SUPER_ADMIN: '超级管理员', NORMAL_USER: '普通用户', ENABLED: '启用', DISABLED: '停用', ARCHIVED: '归档',
  DRAFT: '草稿', READY: '已就绪', ONLINE: '在线', OFFLINE: '离线', SUSPENDED: '暂停上线',
  MAINTENANCE: '维护中', UNKNOWN: '未知', HEALTHY: '健康', DEGRADED: '降级', UNHEALTHY: '异常',
  NORMAL: '正常', PRESSURE: '资源紧张', EXHAUSTED: '资源不足',
  DEPLOYED: '已部署', DEPLOYING: '部署中', DEPLOY_FAILED: '部署失败', REMOVED: '已移除',
  PAUSED: '人工暂停', DRAINING: '排空中', AUTO_EJECTED: '自动摘除', RECOVERING: '恢复观察',
  READY_TO_IMPORT: '可接入', IMPORTED: '已接入', PARSE_FAILED: '解析失败', INVALID: '无效', IGNORED: '已忽略', SUCCESS: '成功',
  AVAILABLE: '可创建', CREATED: '已创建', PARSE_ERROR: '解析异常',
  PRIMARY_STANDBY: '主备模式', LOAD_BALANCE: '负载均衡', PRIMARY: '主服务器', STANDBY: '备用服务器', ACTIVE: '活动节点', CANDIDATE: '候选节点',
  SINGLE: '单节点', SHARDED: '多节点分片', SHARED_ENV_ISOLATED: '共享环境隔离容器', WORKER_POOL: '常驻 Worker 池', DEDICATED_CONTAINER: '独占容器', IDEMPOTENT: '可自动重试', CHECKPOINTABLE: '可断点续跑', MANUAL_CONFIRM: '需人工确认', NON_IDEMPOTENT: '禁止自动重试',
  QUEUED: '排队中', ASSIGNED: '已领取', STARTING: '启动中', RUNNING: '运行中', SUCCEEDED: '成功', PARTIAL_SUCCESS: '部分成功', FAILED: '失败', CANCELLED: '已取消', TIMED_OUT: '超时', LOST: '失联',
  PENDING: '待路由', WAITING_RESOURCE: '等待资源', WARMING_IMAGE: '预热镜像', ROUTED: '已路由', ROUTE_FAILED: '路由失败', ROUTE_CANCELLED: '路由取消',
  OPEN: '已产生', NOTIFYING: '通知中', NOTIFIED: '已通知', ACKED: '已确认', RESOLVED: '已恢复', CLOSED: '已关闭', SUPPRESSED: '已抑制',
  FEISHU: '飞书', WEWORK: '企业微信', DINGTALK: '钉钉', EMAIL: '邮箱', SYSTEM: '系统', COMPANY: '公司', PROJECT: '项目', LOW: '低 IO', HIGH: '高 IO',
}

export function zh(value?: string | number | null): string {
  if (value === null || value === undefined || value === '') return '-'
  return statusText[String(value)] || String(value)
}

export function formatTime(value?: string | null): string {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

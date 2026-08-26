# Release Notes v1.0.98

## 目标

增强平台构建中心异步 Build Job 生命周期，避免构建任务因控制端重启、用户误操作或一次失败而卡死。

## 变更

- 增加构建任务取消接口。
- 增加构建任务重试接口。
- 构建任务详情轮询时自动确认 PENDING 任务后台执行器。
- RUNNING 构建任务超过恢复阈值后自动重新入队。
- 构建任务返回 `canCancel`、`canRetry`、`isTerminal`、`activeInCurrentProcess` 等诊断字段。
- 项目发布页构建任务诊断卡片增加“取消构建”和“重新构建”按钮。
- `.env.example` 和自动配置脚本新增 `CRAWLER_PROJECT_BUILD_STALE_SECONDS`。

## 不变边界

- 不改变 Release / imageDigest 不可变模型。
- 不改变爬虫项目被动构建契约。
- 不实现分布式构建队列；当前仍是控制端本地异步构建执行器。

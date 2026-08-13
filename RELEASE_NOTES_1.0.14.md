# crawler_platform 1.0.14 发布说明

## 版本定位

本版本用于补齐“爬虫项目 CI/CD 多 Agent 发布”后的两个关键使用问题：

1. 开发者推送爬虫项目代码后，执行节点如何快速知道有最新版本。
2. B 服务器上仍有运行中任务时，新镜像更新是否会打断任务，以及是否自动断点续爬。

## 核心结论

- 执行节点通过 Agent 心跳感知新 release，不再要求每台机器 `git pull`。
- 平台在 release 注册后把项目执行节点范围标记为 `OUTDATED`。
- Agent 心跳响应新增 `pendingImagePulls`，用于通知该节点存在待预热镜像。
- Agent 空闲时才主动预热镜像；已有运行实例不会被停止或替换。
- 任务领取后仍按 run 快照中的 `imageRepository@imageDigest` 拉取和校验镜像。
- 断点续爬由业务爬虫通过数据库/Redis checkpoint 实现，平台不做强制中断式迁移。

## 后端变更

- `POST /api/v1/agent-heartbeats` 响应新增：
  - `pendingImagePulls`
  - `imageUpdateCount`
- 新增 Agent 回报接口：
  - `POST /api/v1/agent-image-pull-results`
- `CrawlerProjectServer.image_readiness_status` 增加实际使用状态：
  - `OUTDATED`
  - `WARMING`
  - `READY`
  - `FAILED`
- 修复 Agent 领取任务时过早把镜像状态设为 `READY` 的问题；现在只有真实 pull 与 digest 校验成功后才标记 `READY`。

## Agent 变更

- Agent 会读取心跳响应里的 `pendingImagePulls`。
- 当本机无运行任务且平台标记 `safeToPrewarm=true` 时，Agent 主动拉取并校验新镜像。
- 有运行任务时，Agent 跳过预热，等待空闲，避免抢占资源或打断正在运行的爬虫容器。
- 运行任务启动前拉取镜像成功后，Agent 回报 `READY`。
- 拉取失败时，Agent 回报 `FAILED`，平台保留错误原因，后续空闲心跳可重试。

## 文档

新增：

- `docs/agent-image-update-flow.md`

## 测试

新增覆盖：

- 心跳返回待预热镜像。
- Agent 回报 READY/FAILED 更新项目执行节点范围镜像状态。
- 新 release 注册不会中断旧 digest 的运行中任务。
- 运行中 Agent 收到 `PREWARM_WHEN_IDLE`，不会立即预热。

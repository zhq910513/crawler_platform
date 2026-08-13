# Agent 接入、项目部署与离线兜底说明（1.0.54）

## 角色边界

- 平台超级管理员：维护公司、项目、Release、CI/CD、密钥与全局发布策略。
- 公司运维：通过平台生成的命令安装 Agent，查看节点状态，部署项目 Release 到本公司执行节点，调整部分任务计划。
- 公司操作员：执行任务、暂停/恢复调度、查看日志和失败原因。
- Agent：只作为执行节点，不直接拉源码，不手工运行 Python 文件。

## 新节点接入流程

1. 在平台「执行节点」中打开「Agent 接入向导」。
2. 选择公司，填写节点编码、节点名称、节点服务编码、同时运行任务上限、工作目录、标签与能力。
3. 平台生成一次性安装命令。
4. 公司运维复制命令到目标节点执行。
5. 安装脚本先做 preflight：平台 API 端口、Docker、权限、磁盘、inode、工作目录、本机健康端口、是否已有 Agent。
6. 检查通过后换取 Agent 配置并启动 Agent 容器。
7. 平台通过心跳看到 Agent 在线。

Agent 默认只主动连接平台和镜像仓库，不要求节点所在主机开放公网入站端口。

## 已有 Agent 部署第二个项目

已接入 Agent 的节点不需要重新安装 Agent，也不需要拉项目源码。流程为：

1. 开发者提交 Git tag。
2. CI/CD 构建镜像并注册不可变 Release。
3. 平台项目管理中选择公司、项目、Release 和目标执行节点。
4. 平台创建 Release 部署计划，并把目标执行节点 标记为 OUTDATED。
5. 执行节点心跳获得 pendingImagePulls，空闲时拉取 imageRepository@imageDigest。
6. 拉取成功后回报 READY，失败后回报 FAILED 和错误原因。
7. 任务执行时平台按 releaseId/imageDigest 启动隔离容器。

## 一个执行节点多个项目

一个 Agent 可以承载多个项目。每个项目都必须有独立 Release 和 imageDigest。执行节点执行任务时通过 Docker label、工作目录和运行参数隔离：

- companyId
- projectId
- taskId
- runId
- releaseId
- imageDigest

工作目录建议按公司、项目、运行记录隔离，避免不同项目共享临时目录。

## 离线兜底原则

平台失联时，Agent 不应直接执行完整 sch.py。正确方式是平台在线时下发离线调度快照；Agent 失联后只执行快照中允许离线运行的任务，并且只使用本地已经 READY 的 imageDigest。离线日志和 finish 结果先落本地 spool，平台恢复后补传并对账。

离线任务必须显式配置：

- allowOfflineRun
- offlinePolicy.maxOfflineHours
- offlinePolicy.maxOfflineRuns
- offlinePolicy.catchUp
- offlinePrimaryAgent

非幂等、强依赖平台动态参数或需要人工确认的任务不应开启离线运行。

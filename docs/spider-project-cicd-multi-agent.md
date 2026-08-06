# 爬虫项目 CI/CD 多 Agent 发布规范（crawler_platform 1.0.17）

## 目标

一份爬虫项目代码可能由多台客户服务器执行，因此平台不再把“项目 release”强绑定到单台服务器。标准链路是：CI/CD 构建一次镜像、推送一次 registry、注册一次 release；多个 Agent 节点由平台统一加入项目执行池，并在执行时按 `imageRepository@imageDigest` 拉取同一份镜像。

## 平台端行为

### 项目发现接口

`POST /api/v1/discovered-projects` 支持两种模式：

1. release-only 注册：只提交 `companyId` 与 `manifest`，不提交 `serverCode`。
2. 兼容模式：提交 `serverCode` 或 `serverCodes`，作为初始服务器池提示。

release-only 模式适合 GitHub Actions、GitLab CI 或 Jenkins。它只注册版本和任务定义，不要求操作员在每台设备上拉源码。

### 项目服务器池

已接入项目可以在“项目管理 → 配置执行服务器”中把同公司 Agent 节点加入项目执行池。新加入节点会使用项目最新 release 的 `imageDigest`，初始状态为 `OUTDATED`，Agent 领取任务时会拉取并校验 digest，成功后变为 `READY`。

### Agent 执行

Agent 领取任务时，平台返回：

```text
releaseId
companyId
projectId
projectCode
taskId
taskCode
imageRepository
imageDigest
entryModule
entryFunction
parameters
```

Agent 创建任务容器时注入：

```text
CRAWLER_COMPANY_ID
CRAWLER_PROJECT_ID
CRAWLER_PROJECT_CODE
CRAWLER_TASK_ID
CRAWLER_TASK_CODE
CRAWLER_TASK_GROUP
CRAWLER_RUN_ID
CRAWLER_RELEASE_ID
CRAWLER_IMAGE_REPOSITORY
CRAWLER_IMAGE_DIGEST
CRAWLER_TASK_PARAMS_JSON
```

## 操作员职责

操作员只需要安装一次 Agent，并在平台页面配置任务参数、服务器池、立即执行或调度。操作员不需要在每台设备上 `git pull`，也不需要手工运行 Python 文件。

## 爬虫项目侧要求

`crawler_platform_spiders >= 1.0.7` 应通过 `scripts/platform_register.py` 注册 release；默认不强制传 `serverCode`。生产发布必须使用 registry digest，不建议使用本地 image id。


## 1.0.17 Agent 镜像更新不中断补充

CI/CD 注册新 release 后，平台通过 Agent 心跳返回 `pendingImagePulls` 通知执行节点。Agent 仅在空闲时主动预热镜像；已有运行实例继续使用 run 快照中的旧 digest，不会被新镜像打断。详细规范见 `docs/agent-image-update-flow.md`。

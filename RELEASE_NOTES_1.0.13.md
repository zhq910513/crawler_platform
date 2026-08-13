# crawler_platform 1.0.13 发布说明

本版本在 1.0.12 基础上，专门补齐 `crawler_platform_spiders 1.0.6` 所需的多节点 CI/CD 镜像发布闭环。

## 版本定位

`1.0.13`：爬虫项目多节点镜像发布与 Agent 按 digest 执行整改。

## 核心变化

- `POST /api/v1/discovered-projects` 支持 CI/CD 只注册项目 release，不再强制绑定单台 `serverCode`。
- 保留兼容：仍支持 `serverCode`，并新增 `serverCodes` 批量挂载多个 Agent/服务器。
- 已接入正式项目的新 release 会同步任务定义、release channel，并把已有项目执行节点范围的镜像状态标记为 `OUTDATED`，等待 Agent 按 digest 拉取校验。
- 项目执行节点范围支持把同公司服务器加入已有 release 的执行池；不要求操作员先在每台机器 git pull 或手工部署源码。
- Agent claim 返回新增 `releaseId`，任务容器环境变量新增 `CRAWLER_COMPANY_ID`、`CRAWLER_RELEASE_ID`、`CRAWLER_IMAGE_REPOSITORY`、`CRAWLER_IMAGE_DIGEST`。
- Agent 仍优先按 `imageRepository@imageDigest` 拉取并校验镜像，确保多台设备运行同一份镜像内容。

## 多设备发布流程

标准模式：

```text
开发者提交代码 → CI/CD 构建并推送镜像 → CI/CD 注册 release 到 crawler_platform → 平台选择可执行节点范围 → Agent 按 digest 拉取并执行
```

操作员不再需要在每台设备上拉取爬虫项目代码。

## 测试重点

- release-only 注册，不传 `serverCode`。
- 后续从平台服务器池加入多台 Agent。
- 多 Agent 领取任务时使用同一个 `imageDigest`。
- 新 release 发布后已有项目服务器状态变为 `OUTDATED`，执行时由 Agent 拉取并校验。
- 旧 `serverCode` 注册方式保持兼容。

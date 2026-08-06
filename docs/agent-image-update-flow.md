# Agent 镜像更新与不中断运行规范（crawler_platform 1.0.17）

## 目标

当开发者推送爬虫项目代码后，执行服务器不再通过 `git pull` 判断是否更新，而是通过平台 release 与 Agent 心跳感知最新镜像 digest。

标准链路：

1. 开发者 `git push`。
2. CI/CD 构建并推送镜像，得到 `imageDigest`。
3. CI/CD 调用 `POST /api/v1/discovered-projects` 注册 release。
4. 平台把项目服务器池中对应节点标记为 `OUTDATED`。
5. Agent 下一次心跳收到 `pendingImagePulls`。
6. Agent 空闲时预热镜像；如果任务已经运行，不打断运行实例。
7. 新任务启动前仍会按 run 快照中的 `imageRepository@imageDigest` 拉取并校验。
8. Agent 通过 `POST /api/v1/agent-image-pull-results` 回报 `READY/FAILED`。

## 问题一：执行服务器如何快速知道有最新版本

执行服务器通过 Agent 心跳知道。平台心跳响应包含：

```json
{
  "pendingImagePulls": [
    {
      "projectId": 1,
      "projectCode": "crawler_platform_spiders",
      "releaseId": 12,
      "releaseVersion": "1.0.7",
      "imageRepository": "registry.example.com/crawler_platform_spiders",
      "imageDigest": "sha256:...",
      "imageReadinessStatus": "OUTDATED",
      "action": "PREWARM_NOW",
      "safeToPrewarm": true
    }
  ]
}
```

默认 Agent 心跳间隔较短，因此 CI 注册 release 后，各执行服务器通常会在下一次心跳内知道有新镜像。

## 问题二：B 服务器正在执行任务时是否会被打断

不会。

平台和 Agent 的规则是：

- 已经创建的 run 会保存自己的 `releaseId/imageDigest` 快照。
- 项目发布新 release 后，只影响后续新 run。
- B 服务器上正在运行的容器不会被停止、重启或替换。
- Agent 心跳发现有运行实例时，只返回 `PREWARM_WHEN_IDLE`，默认不执行预热。
- 任务结束后，Agent 空闲，再拉取新镜像。

## 关于断点续爬

镜像更新不会自动把正在运行的任务迁移到新镜像，也不会自动重启任务。断点续爬必须由业务爬虫实现：

- 已处理主键写入数据库。
- 分页游标写入 Redis/MySQL。
- 文件下载任务记录状态。
- 重试任务根据 checkpoint 从上次位置继续。

平台只保证：镜像更新不打断运行实例；失败或重试时使用 run 快照中的 digest，避免同一个运行实例前后代码不一致。

## 状态语义

- `OUTDATED`：平台已发现新 digest，Agent 尚未完成拉取。
- `WARMING`：Agent 已领取任务或正在预热镜像。
- `READY`：Agent 已完成 digest 拉取和校验。
- `FAILED`：Agent 拉取或校验失败，后续心跳会继续提示可重试。

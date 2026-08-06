# crawler_platform 1.0.16 发布说明

## 版本定位

本版本继续完善爬虫平台与通用爬虫项目的多 Agent 镜像发布闭环，重点修复商业交付中的发布不可变性、Agent 重启误判 LOST 与结果回传抗故障能力。

## 核心优化

- CI/CD release 注册增加不可变语义：同一 project + releaseVersion 禁止覆盖不同 imageDigest / imageRepository / gitCommit。
- releaseVersion 必须为 `x.y.z` 语义版本，禁止 `main`、`latest`、`dev`、`v1.0.16` 等浮动或带前缀版本直接注册。
- Agent 心跳会扫描 Docker 中仍在运行且带 `crawler.platform.run_id` 标签的任务容器。
- Agent 进程重启后，如果平台能从心跳中看到对应 runId 仍在 Docker 中运行，不再立即把该 run 标记为 LOST。
- Agent 最终 `finish` 回传遇平台短暂不可用时会写入本地 spool，后续心跳自动补传，降低“实际成功但平台标记 LOST”的概率。
- 文档同步明确：发布版本不可变、运行中任务不中断、新任务使用新 digest、断点续爬由业务 checkpoint 实现。

## 兼容说明

- 数据库结构无新增迁移。
- 已有 1.0.14 release 和执行记录不受影响。
- 后续 CI/CD 应使用 Git tag `v1.0.16` 发布，但平台注册的 releaseVersion 必须是不带 `v` 的 `1.0.16`。

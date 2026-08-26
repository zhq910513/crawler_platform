# 平台构建中心任务生命周期增强 v1.0.98

## 背景

v1.0.97 将项目发布中的镜像构建改成异步 Build Job，解决了前端 30 秒 HTTP 超时问题。但异步构建进入真实运行后，还需要处理三个生产场景：

1. 用户误点发布后需要取消构建。
2. 构建失败后需要从同一仓库和分支重新构建，而不是重新填写表单。
3. 控制端进程重启后，处于 PENDING 或长时间 RUNNING 的构建任务不能永久卡死。

## 本版改动

v1.0.98 增加 Build Job 生命周期控制：

- `GET /api/v1/project-builds/{buildJobId}` 会对 PENDING 任务进行自动恢复，确保轮询时后台执行器存在。
- 对超过 `CRAWLER_PROJECT_BUILD_STALE_SECONDS` 的 RUNNING 任务自动重新入队，从源码拉取阶段重新构建。
- 新增取消接口：`POST /api/v1/project-builds/{buildJobId}/cancellations`。
- 新增重试接口：`POST /api/v1/project-builds/{buildJobId}/retries`。
- 项目发布页的“构建任务诊断”卡片增加“取消构建”和“重新构建”动作。

## 状态语义

- `PENDING`：已入队，允许取消；轮询时会自动确认后台执行器。
- `RUNNING`：正在构建，允许取消；若控制端异常中断且超过恢复阈值，会自动重新入队。
- `SUCCEEDED`：构建成功并已登记 Release。
- `FAILED`：构建失败，允许重新构建。
- `CANCELED`：用户取消，允许重新构建。

## 恢复边界

自动恢复不会热切换已有 Run，也不会覆盖历史 Release。被恢复的 Build Job 会从源码拉取开始重新构建，并继续遵循不可变 Release / imageDigest 规则。

`CRAWLER_PROJECT_BUILD_STALE_SECONDS` 默认使用 `CRAWLER_PROJECT_BUILD_TIMEOUT_SECONDS + 60`，用于避免长时间 Docker build 被误判为中断。部署脚本会自动写入该配置。

# v1.0.97 项目发布异步构建轮询修复

## 背景

点击“发布项目”后，如果当前仓库尚未登记 Release，平台需要执行 git clone、被动构建契约、Docker build、Docker push、digest inspect 和 Release 登记。该链路天然可能超过前端 30 秒 HTTP 超时。

## 修复

- 项目发布不再在一次 HTTP 请求内同步执行完整镜像构建。
- `POST /api/v1/project-publish/pipelines` 在需要构建时只创建 Build Job 并立即返回 `pipelineStatus=BUILDING`。
- 后端使用后台线程继续执行构建、推送和 Release 登记。
- 前端在收到 `BUILDING` 后轮询 `GET /api/v1/project-builds/{buildJobId}`。
- 构建成功后前端自动再次调用发布流水线，继续项目接入、Release 部署和节点自检。
- 构建失败时前端展示 `buildJob.errorMessage` 和最近构建日志。

## 边界

当前仍是单控制端进程内后台执行器，不是持久化分布式构建队列。容器重启可能中断正在执行的构建任务；后续版本应补构建任务恢复和独立 worker。

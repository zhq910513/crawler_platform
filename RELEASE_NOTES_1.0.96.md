# crawler_platform v1.0.96

## 目标

补齐平台构建中心可观测性。v1.0.95 已经允许 docker CLI 缺失时通过 Docker Engine API 兜底，但构建真正执行失败时，项目发布页仍可能只看到简短错误，无法直接定位失败阶段。

## 变更

- 构建中心 readiness 返回 executor diagnostics：git、docker CLI、docker daemon、Docker Socket、Engine API、选中执行器、镜像仓库前缀和构建根目录。
- 构建失败时，`project-publish/pipelines` 的错误响应会携带 `buildJob`、`buildLogs`、当前阶段和原始错误数据。
- 项目发布页新增“构建任务诊断”卡片，直接展示构建任务状态、阶段、错误和最近构建日志。
- 保留 Release 级不可变发布原则：构建失败不会登记 Release，不会向执行节点下发部署指令。

## 边界

- 仍未引入私有 Git 凭据数据库模型。
- 仍未引入异步构建队列和实时 SSE 日志流。
- 当前构建执行器仍是同步本地 Docker / Docker Engine API。

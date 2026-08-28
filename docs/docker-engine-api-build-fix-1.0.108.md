# Docker Engine API 构建修复（v1.0.108）

构建中心运行于没有 Docker CLI、但挂载 `/var/run/docker.sock` 的容器时，通过 `DockerEngineClient` 调用 Engine API。

v1.0.108 将 build/push/inspect 请求改为先读取 daemon `/version`，再使用 daemon 返回的 `ApiVersion` 构造 `/v<version>/...` 请求；如果设置 `DOCKER_API_VERSION`，则使用显式版本。Engine API build 同时传递 `version=2`，使用 BuildKit 与 CLI 路径保持一致。

Docker 28 的 JSON progress stream 已弃用顶层 `error` 字段，因此错误判断以 `errorDetail.message` 为主并兼容旧 `error` 字段。

发生构建失败时，`DOCKER_BUILD_API` 日志以 `exitCode=1` 保存真实 daemon 错误，随后才抛出平台级 `Docker Engine API 构建失败`，使 UI 同时保留用户可读阶段和底层诊断。

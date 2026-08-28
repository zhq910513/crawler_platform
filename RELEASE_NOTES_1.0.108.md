# crawler_platform v1.0.108

## Docker Engine API 构建兼容性与失败诊断

- Docker Engine API build/push/inspect 在请求前读取 `/version`，使用 daemon 返回的 `ApiVersion` 生成版本化 API 路径；同时尊重显式 `DOCKER_API_VERSION`。
- Engine API `POST /build` 显式传递 `version=2` 使用 BuildKit，与 Docker CLI 路径的 `DOCKER_BUILDKIT=1` 保持一致，不再隐式落到默认 classic builder。
- Docker stream 错误同时识别 `errorDetail.message` 与旧版 `error` 字段，兼容 Docker 28 对顶层 `error` 字段的弃用行为。
- Engine API HTTP 非 2xx 响应提取 JSON `message` 并携带 HTTP 状态，避免只显示原始响应体。
- Unix socket、超时和 HTTP 协议异常统一包装为 `DockerEngineError`，保留请求方法和路径。
- build/push/inspect 失败会在 Build Job 中写入失败阶段日志；发布助手可直接显示 daemon 返回的真实错误，不再只显示“Docker Engine API 构建失败”。

## 兼容性

- 不改变爬虫项目被动构建契约、manifest 格式、Release 不可变语义和 registry 命名规则。
- Docker CLI 可用时仍优先使用现有 CLI 构建路径；本次只修正无 CLI 场景下的 Engine API fallback。

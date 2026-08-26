# Release Notes v1.0.103

## 目标

修复项目构建进入 Docker build 阶段后只显示“Docker Engine API 构建失败”但缺少真实失败原因的问题，并在代码层补齐基础镜像预拉取、构建上下文诊断和 Docker Engine API 失败日志回传。

## 改动

- Docker Engine API client 保留 build/pull/push JSON stream 的可读日志尾部。
- Docker Engine API build 失败时写入 `DOCKER_BUILD_API` 失败日志，不再只写最终 `FAILED`。
- 构建前新增 `DOCKER_CONTEXT`：展示 Dockerfile、基础镜像、构建平台、上下文估算、执行器。
- 构建前新增基础镜像预检查 / 预拉取日志 `DOCKER_PULL`。
- 新增配置：
  - `CRAWLER_PROJECT_DOCKER_PULL_ATTEMPTS=2`
  - `CRAWLER_PROJECT_DOCKER_PULL_RETRY_SECONDS=5`
- Docker Engine API tar context 开始尊重常见 `.dockerignore` 规则，避免 API 构建路径和 docker CLI 构建路径差异过大。

## 边界

如果控制端 Docker daemon 无法访问 Docker Hub 或镜像源，代码无法凭空获取基础镜像；本版本会把该根因直接暴露到构建任务日志，并允许通过预热基础镜像或配置镜像源解决。

# 项目构建 Docker 诊断增强 v1.0.103

v1.0.103 聚焦 Docker build 阶段的可观测性和可恢复性。

构建任务现在会在进入 Docker build 前输出：

- `DOCKER_CONTEXT`：Dockerfile 是否存在、解析到的基础镜像、构建平台、上下文大小估算、当前使用 CLI 还是 Engine API。
- `DOCKER_PULL`：基础镜像本地是否已存在；不存在时尝试预拉取并记录失败原因。
- `DOCKER_BUILD_API`：Docker Engine API build 的完整错误尾部。

这可以区分三类问题：

1. 构建上下文 / Dockerfile 问题。
2. 基础镜像无法从 Docker Hub 或镜像源拉取。
3. Docker Engine API / Docker socket / daemon 权限问题。

平台不会默认接入非官方第三方基础镜像，因为这会引入供应链风险。生产环境建议通过 Docker daemon 镜像源、内网 registry 或预热基础镜像解决外网不稳定问题。

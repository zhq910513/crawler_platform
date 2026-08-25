# crawler_platform v1.0.95

## 目标

修复平台构建中心在 API 容器内缺少 `docker` CLI 时继续阻断项目发布的问题。

## 背景

v1.0.94 已经将构建中心基础配置纳入部署脚本，并在 `docker-compose.yml` 中为 API 容器挂载 `/var/run/docker.sock`。现场返回显示：

```text
平台构建中心未就绪：Docker 命令不可用：docker
```

这说明平台后端把“必须存在 docker 命令”作为硬阻断。该判断过严：只要 API 容器已经挂载 Docker Socket，就可以直接调用 Docker Engine API 完成 build / push / inspect，不必依赖容器内 `docker` CLI。

## 改动

- 新增 `backend/app/services/docker_engine_client.py`。
- 构建中心 readiness 从“必须有 docker CLI”改为“docker CLI 可用或 Docker Socket API 可用”。
- `docker build` / `docker push` / `docker image inspect` 增加 Docker Engine API fallback。
- 发布助手返回的 `buildExecutor` 改为 `LOCAL_DOCKER_CLI_OR_ENGINE_API`。
- 阻断文案改为只有当 `docker` 命令和 `/var/run/docker.sock` 都不可用时才提示 Docker 执行器不可用。
- 增加防回归测试 `backend/tests/test_project_build_center_docker_api_fallback_1095.py`。

## 边界

- 仍然需要 API 容器挂载 `/var/run/docker.sock`。
- 仍然需要构建环境可访问 Git 仓库和 registry。
- Docker Socket 等价宿主机 root 权限，这仍然是构建中心的基础设施安全边界。

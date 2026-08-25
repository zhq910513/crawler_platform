# crawler_platform v1.0.94

## 目标

修正 v1.0.92/v1.0.93 中“构建中心最小闭环仍要求服务器手动改 `.env`、手动确认 Docker CLI / Socket / registry 前缀”的问题。

v1.0.94 的原则：

- 平台部署脚本自动启用爬虫项目构建中心。
- 平台部署脚本自动补齐构建目录和内置 registry 镜像仓库前缀。
- API 容器自动具备 Git / Docker CLI，并挂载宿主 Docker Socket。
- 构建中心默认使用本机 registry 推送，再把对外可访问 registry 仓库写入 Release manifest。
- 仍不恢复爬虫项目主动 CI/CD，不要求业务仓库保存平台 Token。

## 改动

### 部署自动化

新增：

```text
部署脚本会调用 deploy/scripts/configure-project-build-center.sh
```

自动写入或修正：

```env
CRAWLER_PROJECT_BUILD_ENABLED=1
CRAWLER_PROJECT_BUILD_ROOT=/data/project-builds
CRAWLER_PROJECT_BUILD_TIMEOUT_SECONDS=1800
CRAWLER_PROJECT_IMAGE_REPOSITORY_PREFIX=<registry-host>:5000/crawler_projects
CRAWLER_AGENT_REGISTRY_PUBLIC_HOST=<推导出的 registry host>
```

接入脚本：

```text
deploy/scripts/sync-runtime-version.sh
deploy/scripts/prepare.sh
deploy/scripts/deploy-single-server.sh
```

### 容器能力

`backend/Dockerfile` 安装：

```text
git
docker.io
```

`docker-compose.yml` 为 API 服务挂载：

```text
./data/project-builds:/data/project-builds
/var/run/docker.sock:/var/run/docker.sock
```

API 服务以 root 访问 Docker Socket。Docker Socket 本身等价宿主 root 权限，因此这不是新增额外权限假象，而是构建中心所需能力的显式化。

### 构建中心执行逻辑

- 支持从 `CRAWLER_PROJECT_IMAGE_REPOSITORY_PREFIX`、`CRAWLER_AGENT_REGISTRY_PUBLIC_HOST`、`CRAWLER_CONTROL_PUBLIC_BASE_URL` 推导 Release 对外镜像仓库。
- 对平台内置 registry，构建中心向 `localhost:5000/crawler_projects/...` 推送，避免控制端宿主 Docker 因 HTTP public registry 未配置 insecure registry 而失败。
- 最终 manifest 仍写入执行节点可访问的对外镜像仓库地址。

## 未完成

仍未实现：

- 私有 Git 仓库凭据数据库模型。
- 外部镜像仓库账号密码数据库模型。
- 异步构建队列和实时日志流。
- 取消构建。

这些属于后续版本，不应该通过手写爬虫项目 CI/CD 规避。

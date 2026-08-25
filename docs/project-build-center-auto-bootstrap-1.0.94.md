# v1.0.94 平台构建中心自动启用说明

## 背景

v1.0.92 打通了平台构建中心最小闭环，但仍需要在服务器上手动开启 `CRAWLER_PROJECT_BUILD_ENABLED=1`、配置 `CRAWLER_PROJECT_IMAGE_REPOSITORY_PREFIX`、准备构建目录以及确认 API 容器中的 Docker 能力。

v1.0.94 将这些动作纳入平台部署代码。

## 自动动作

发布或准备脚本会调用：

```bash
bash deploy/scripts/configure-project-build-center.sh .env
```

该脚本会自动：

1. 启用 `CRAWLER_PROJECT_BUILD_ENABLED=1`。
2. 设置 `CRAWLER_PROJECT_BUILD_ROOT=/data/project-builds`。
3. 创建宿主挂载目录 `data/project-builds`。
4. 从 `CRAWLER_AGENT_REGISTRY_PUBLIC_HOST`、`CRAWLER_CONTROL_PUBLIC_BASE_URL`、`CP_DEPLOY_PUBLIC_HOST` 或本机 IP 推导 registry host。
5. 设置 `CRAWLER_PROJECT_IMAGE_REPOSITORY_PREFIX=<host>:5000/crawler_projects`。

## Docker 能力

API 容器需要执行：

```bash
git clone
docker build
docker push
docker image inspect
```

因此：

- backend 镜像内置 `git` 和 `docker.io`。
- API 容器挂载 `/var/run/docker.sock`。
- API 容器挂载 `./data/project-builds:/data/project-builds`。

## Registry 推送策略

为了避免本机 Docker 对 `http://<公网IP>:5000` 的 insecure registry 配置依赖，平台内置 registry 默认采用：

```text
本机推送：localhost:5000/crawler_projects/<projectCode>:<releaseVersion>
对外 manifest：<registry-public-host>:5000/crawler_projects/<projectCode>@sha256:...
```

两者访问的是同一个 registry 数据；执行节点使用对外地址拉取。

## 仍需人工的边界

v1.0.94 不再要求手动改 `.env` 开启构建中心，但仍无法自动处理所有基础设施事实：

- 云安全组是否开放 5000/TCP。
- 私有 Git 仓库账号权限。
- 外部镜像仓库账号权限。

这些需要后续进入平台凭据模型，而不是写到爬虫项目仓库。

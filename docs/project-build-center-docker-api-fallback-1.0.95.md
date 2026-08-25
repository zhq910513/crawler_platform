# v1.0.95 平台构建中心 Docker Engine API fallback

## 问题

现场项目发布分析返回：

```text
平台构建中心未就绪：Docker 命令不可用：docker
```

这类阻断通常发生在 API 容器没有安装 `docker` CLI，或者没有使用 v1.0.94 之后的新后端镜像时。

## 修复原则

平台构建中心真正需要的是 Docker daemon 能力，不是必须依赖 `docker` CLI 二进制。

因此 v1.0.95 支持两条执行路径：

```text
优先：docker CLI + Docker daemon
兜底：/var/run/docker.sock + Docker Engine HTTP API
```

## 新执行器判断

构建中心 readiness 现在只在以下情况阻断：

```text
既没有可用 docker CLI，也没有可访问的 /var/run/docker.sock
```

如果 API 容器没有 `docker` 命令，但已挂载 Docker Socket，发布助手应进入 `PLATFORM_BUILD_CENTER_READY`。

## 能力范围

Docker Engine API fallback 覆盖：

```text
POST /build
POST /images/{name}/push
GET  /images/{name}/json
```

对应平台动作：

```text
构建项目镜像
推送到 registry
读取 RepoDigests 作为不可变 imageDigest
```

## 仍需满足的事实

- API 容器必须挂载 `/var/run/docker.sock`。
- 构建宿主机必须能访问目标 Git 仓库。
- 构建宿主机必须能推送到目标 registry。
- 执行节点必须能拉取最终 `imageRepository@imageDigest`。

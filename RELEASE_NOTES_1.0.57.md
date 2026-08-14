# crawler_platform 1.0.58 自动部署流程线安全修复

## 修复内容

- 修复 Agent 安装脚本检查 Docker `insecure-registries` 时的错误引用，避免 `/etc/docker/daemon.json` 已配置 registry 但被误判为未配置。
- 同步修复后端安装脚本模板与部署脚本安装器。
- 保留 1.0.56 的 Agent 镜像自动准备、部署强门禁、失败阶段标识、授权式 Docker registry 配置和授权式替换 Agent 容器能力。
- 版本统一递增到 1.0.58。

## 自动化边界

- 平台可自动处理：Agent 镜像构建、tag、push、写入 `.env`、重启后端服务、registry tag 验证。
- 节点脚本授权后处理：备份并合并 Docker `insecure-registries`、重启 Docker、替换已有 Agent 容器。
- 仍需人工处理：云安全组/防火墙端口放行，除非后续接入云厂商 API 并获得明确授权。

# Release Notes 1.0.55

## Agent 镜像分发自动化与节点安装授权

- 新增 `deploy/scripts/prepare-agent-image.sh`，用于在平台服务器自动构建 Agent 镜像、启动/复用内置 registry、推送镜像、写入 `.env` 的 `CRAWLER_AGENT_IMAGE` 并按需重启后端服务。
- 运行总览平台自检新增自动化处理分类，区分平台脚本可处理、节点安装脚本可处理、需要云控制台处理和需要人工确认处理。
- Agent 安装脚本新增 `--auto-configure-docker-registry`，在授权后可自动备份并合并 Docker `insecure-registries` 配置，然后重启 Docker 并继续拉取 Agent 镜像。
- 部署脚本在部署后尝试自动准备 Agent 镜像；无法推导公网 registry 时不阻断平台启动，但会在运行总览展示明确处理动作。
- 版本同步到 1.0.55。

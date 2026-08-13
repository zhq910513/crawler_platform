# crawler_platform 1.0.47

## Agent 镜像下发与版本对齐修复

- 修复后端安装脚本模板残留 `crawler_platform_agent:1.0.44` 的问题。
- 安装脚本 `/api/v1/agent-installers/linux.sh` 改为按运行时配置动态注入 Agent 镜像。
- Agent bootstrap `.env` 增加 `AGENT_IMAGE` 和 `AGENT_AGENT_VERSION`，确保远程节点拉取镜像与当前平台版本一致。
- 新增 `CRAWLER_AGENT_IMAGE` 配置项，支持生产环境指定私有镜像仓库地址。
- 继续保持控制端访问入口统一和外部端口保留逻辑。

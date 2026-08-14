# crawler_platform 1.0.56 自动部署流程线安全加固

- Agent 接入命令默认携带授权式 Docker registry 自动配置参数和已有 Agent 替换参数，减少手动步骤。
- 安装脚本增加接入阶段标识，失败时输出失败阶段，便于定位控制端、Docker、配置换取、镜像拉取、容器启动等问题。
- 安装脚本替换已有 Agent 容器前需要明确参数授权，避免静默中断运行中的 Agent。
- Agent 镜像准备脚本增加精确 tag 验证和更安全的 .env 写入方式，避免 sed 特殊字符替换风险。
- 部署/升级脚本支持 STRICT_AGENT_IMAGE_PREPARE=1，在需要强门禁时可让 Agent 镜像准备失败直接阻断发布。

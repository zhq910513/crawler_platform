# 1.0.48 硬编码配置审查与 Agent 接入失败兜底修复

## 修复内容

- 移除 Agent 运行配置里默认 `http://api:8000` 的隐式控制端地址，避免独立执行节点缺少 `AGENT_CONTROL_PLANE_URL` 时误连内部 Compose 服务名。
- Agent 安装脚本在镜像拉取失败且本机不存在镜像时改为明确失败退出，不再继续执行 `docker run` 产生二次错误。
- 后端运行配置新增 `crawler_agent_version`，bootstrap `.env` 下发 `AGENT_AGENT_VERSION` 时使用 Agent 版本配置，不再直接复用平台 API 版本字段。
- 后端配置读取 `CRAWLER_AGENT_IMAGE / AGENT_IMAGE / AGENT_AGENT_VERSION / APP_VERSION` 时忽略空字符串，避免 `.env` 写了空值导致下发空镜像地址。
- 更新 Agent `.env.example`，不再把远程执行节点示例写成 `127.0.0.1:8000`。
- 平台、前端、Compose、Agent、部署脚本版本同步到 `1.0.48`。
- 同步 README 与当前运维文档标题版本到 `1.0.48`，避免上线文档继续引用 1.0.46 造成版本判断混乱。

## 风险控制

- 保留内部 API 健康检查 `http://127.0.0.1:8000/health`，该地址只在容器内部使用，不作为公网接入地址。
- 保留无仓库前缀 Agent 镜像的警告；如果远程节点无法访问 Docker Hub，必须配置 `CRAWLER_AGENT_IMAGE` 为可访问私有仓库镜像。

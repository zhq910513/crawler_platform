# crawler_platform 1.0.71

## 执行节点接入与清理链路修复

- Agent 安装脚本在消耗一次性 Join Token 前先验证 Registry 网络，所有 curl 检测增加连接/总时长硬超时。
- Docker HTTP Registry 配置改为显式授权；默认不修改 `/etc/docker/daemon.json`、不重启 Docker。
- 修正“Docker 重启成功 = Registry 可访问”的假 PASS，`docker pull` 失败保留真实 Docker 错误。
- 运行自检不再把配置中的 `CRAWLER_AGENT_IMAGE_DIGEST` 当成 Registry 已就绪证据；真实查询 tag/manifest，并支持内置 Registry 公网地址在控制端 NAT 回环失败时回退 localhost 验证。
- 正式 Agent Registry 不再静默复用 smoke 容器；历史 smoke registry 可原地安全接管为正式 registry，新建正式 registry 使用持久化数据卷。

## 执行节点页面与删除语义

- 执行节点列表压缩为节点、状态、资源、运行任务、最后心跳、最近异常和操作；没有 Agent 心跳时资源显示 `-`，不再伪装成 `0%`。
- `CONFIG_ISSUED` 等内部接入状态改为用户语义“接入中 / 等待首次心跳”。
- 接入记录仅展示待接入、接入中、接入失败；孤立邀请支持物理清理，清理后立即从列表消失。
- 在线节点删除仅对明确上报 `agentDecommission` 能力的新版 Agent 自动下发退役指令；Agent 无运行任务时关闭自身重启策略、确认后平台删除节点/Agent/邀请，再清理失效 `.env` 并移除自身容器。
- 旧版在线 Agent 未声明退役能力时不强发未知指令；平台立即使旧 Token 失效并删除平台记录，同时返回目标机本地清理命令，避免节点长期卡在“清理失败”。
- 离线或从未上线节点无法远端确认清理时，平台立即使旧 Token 失效并删除平台记录，同时返回仅清理 Agent 容器和失效 `.env` 的本机命令，不删除业务数据目录。
- 前端时间统一把后端无时区标记的 UTC ISO 时间按 UTC 解析后再转换为浏览器本地时区，修复页面时间少 8 小时的问题。

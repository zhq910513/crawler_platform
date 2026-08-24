# crawler_platform v1.0.82 发布说明

v1.0.82 是在 v1.0.81 执行节点接入体验修复版基础上的接入身份保护修复版，重点处理目标机已有 `/opt/crawler-agent/.env` 时，安装脚本复用旧长期 Agent 凭据导致新 Join Token 未被消费、新接入记录一直停留在“待接入/接入中”的问题。

## 变更

1. 安装脚本复用长期 Agent 凭据时，会携带当前 `joinToken` 调用 `/api/v1/agent-bootstrap/resume-env?joinToken=...`。
2. 控制端在续跑旧凭据前校验当前 Join Token 对应的 `serverCode/agentCode` 是否与本机长期凭据一致。
3. 如果本机旧凭据不属于当前接入命令，控制端返回 409，安装脚本自动回落到本次 Join Token 正常换取新 Agent 配置。
4. 安装脚本新增非敏感诊断输出：`server / agent / image`，避免现场误判是否仍在复用旧配置。
5. 接入配置已下发但超过 5 分钟仍未收到首轮心跳时，接入记录自动从“接入中”转为“接入失败”，并提示查看目标机 `docker logs --tail 200 crawler-agent`。
6. 平台版本统一提升到 `1.0.82`。

## 测试

- Python 编译检查通过。
- Shell `bash -n` 检查通过。
- 关键接入契约测试通过：12 passed。
- Agent Join Token / bootstrap 相关回归测试通过：6 passed。
- 版本一致性检查通过：`releaseVersion=1.0.82`，`warnings=0`。

## 现场注意

如果目标机仍显示“接入中”，优先检查：

```bash
docker logs --tail 200 crawler-agent
docker inspect -f '{{.Config.Image}}' crawler-agent
cat /opt/crawler-agent/.env | grep -E 'AGENT_AGENT_CODE|AGENT_SERVER_CODE|AGENT_IMAGE|AGENT_CONTROL_PLANE_URL'
```

如生产 `.env` 仍配置 `CRAWLER_AGENT_IMAGE=42.193.226.138:5000/crawler_platform_agent:1.0.71`，生成命令仍会拉取 `1.0.71` Agent 镜像。Agent 版本独立于平台版本，但需要确认该 Agent 镜像与当前控制端 API 契约兼容。

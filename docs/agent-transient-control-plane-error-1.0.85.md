# v1.0.85 执行节点瞬时控制端连接异常处理

## 现场现象

执行节点已经显示在线，资源指标正常，最后心跳时间也在持续刷新，但“最近异常”列出现：

```text
Agent 主循环异常：HTTPConnectionPool(host='42.193.226.138', port=8080): Max retries exceeded with url: /api/v1/agent-heartbeats ... Connection refused
```

## 判断

该日志说明 Agent 某一次访问控制端心跳接口时，控制端 `8080` 端口短暂拒绝连接。常见原因包括：

- 控制端服务正在重启。
- Docker Compose 滚动更新期间端口短暂不可用。
- 反向代理或防火墙短暂拒绝连接。
- 控制端进程重启但 Agent 心跳刚好打到不可用窗口。

如果后续“最后心跳”已刷新，说明 Agent 到控制端的链路已经恢复。这类历史异常不应继续作为当前“最近异常”展示。

## 本轮修复

### Agent 侧

- `PlatformUnavailable` 单独处理。
- 控制端临时不可达只写日志，不写入 `lastError`。
- 鉴权失败和真实主循环异常仍然写入 `lastError`。

### 控制端

- 成功收到心跳时，对旧 Agent 上报的瞬时网络异常做归一化处理。
- 匹配范围限制在 `Agent 主循环异常` 且包含 `/api/v1/agent-heartbeats` 或 `/api/v1/agent-run-claims` 的控制端连接异常。
- 不清洗 Docker、任务执行、凭据、指令执行等真实异常。

### 前端

- 在线节点隐藏已恢复的瞬时控制端连接异常。
- 最近异常列增加 `show-overflow-tooltip`，避免长异常撑开表格。

## 验证建议

部署 v1.0.85 后：

```bash
docker logs --tail 200 crawler-agent
docker exec crawler-agent env | grep -E 'AGENT_CONTROL|AGENT_AGENT|AGENT_SERVER|AGENT_HOST|AGENT_IMAGE'
```

若控制台最后心跳持续刷新，且最近异常为空，说明恢复正常。

如果连接异常持续出现，继续检查控制端：

```bash
curl -fsS http://42.193.226.138:8080/health && echo
docker compose ps
docker compose logs --tail 200 api
```

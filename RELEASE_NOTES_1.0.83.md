# crawler_platform 1.0.83

## 变更

- 修复主布局使用 KeepAlive 导致侧边导航切换后页面不重新加载的问题；导航切换会重新挂载页面，点击当前导航项也会强制刷新当前页面实例。
- 所有 GET 请求统一增加 no-cache 请求头和 `_t` 时间戳，降低浏览器、代理或网关缓存导致“刷新按钮没反应”的风险。
- 执行节点页面刷新按钮增加 loading 状态和刷新成功反馈。
- 执行节点页面在存在待接入/接入中记录时自动轮询列表，避免只能依赖手工刷新确认首轮心跳。
- 执行节点状态提示补充心跳触发说明：Agent 容器启动进入主循环后会立即发起心跳，默认每 10 秒一次。

## 心跳说明

Agent 容器启动后执行 `crawler_agent.main.AgentApp.loop()`，`last_heartbeat = 0.0`，首次循环满足 `now - last_heartbeat >= heartbeat_interval_seconds`，因此会立即调用 `/api/v1/agent-heartbeats`。后续心跳默认间隔由 `AGENT_HEARTBEAT_INTERVAL_SECONDS` 控制，默认 10 秒。

如果控制台超过 30 秒仍显示“接入中/等待首次心跳”，通常说明 Agent 容器没有正常进入主循环、心跳请求被 401/网络/Docker 权限等问题阻断，或目标机仍在复用旧凭据/旧镜像。优先查看：

```bash
docker logs --tail 200 crawler-agent
docker inspect -f '{{.Config.Image}}' crawler-agent
docker exec crawler-agent env | grep -E 'AGENT_CONTROL|AGENT_AGENT|AGENT_SERVER|AGENT_IMAGE'
```

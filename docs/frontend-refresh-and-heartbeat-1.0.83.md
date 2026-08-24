# 前端刷新与 Agent 首轮心跳修复说明（1.0.83）

## 问题

1. 执行节点接入后页面经常停留在“等待首次心跳”，用户需要手工多次刷新才能确认状态。
2. 侧边导航切换页面时，部分页面由于 KeepAlive 缓存没有重新加载，执行节点页表现最明显。
3. 多个刷新按钮虽然调用了接口，但缺少统一防缓存策略和可见反馈，用户感知为“没起作用”。

## 修复

- 主布局不再对业务页使用 KeepAlive，路由切换时通过 `route.fullPath + viewReloadKey` 重新挂载页面。
- 点击当前侧边导航项时递增 `viewReloadKey`，强制重建当前页面。
- Axios GET 请求统一写入 `Cache-Control: no-cache`、`Pragma: no-cache` 和 `_t=Date.now()`。
- 执行节点页刷新按钮增加 loading 和成功提示。
- 执行节点页发现待接入/接入中记录时，每 10 秒静默刷新一次，直到状态收敛。
- 执行节点状态提示明确心跳触发机制：容器启动进入主循环后立即心跳，默认每 10 秒一次。

## 边界

本次没有修改 Agent 心跳 API 契约，也没有修改 Agent 镜像版本策略。若现场继续拉取旧 Agent 镜像，需要检查生产 `.env` 中 `AGENT_AGENT_VERSION` 和 `CRAWLER_AGENT_IMAGE`。

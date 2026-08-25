# Agent 观测远端地址兜底修复 1.0.91

## 问题

v1.0.90 中，项目发布页要求部署节点必须具备可展示地址，避免“节点地址采集中”仍显示“可部署”。但现场存在旧 Agent 镜像已经在线、资源指标正常，却没有上报 `hostIp/publicIp/hostname` 的情况。

这会导致执行节点页显示在线，但项目发布页仍阻断为“节点地址采集中”。

## 设计判断

执行节点已完成心跳时，控制端至少可以观测到一次心跳请求的来源 IP。该地址不是最优的宿主机默认网卡地址，但在旧 Agent 不具备主机身份上报能力时，可作为部署诊断与发布门禁的安全兜底。

地址优先级：

```text
Agent 上报 hostIp
→ Agent 上报 publicIp
→ 控制端观测远端 IP
→ Agent 上报 hostname
→ 手动填写 serverIp
```

其中控制端观测远端 IP 只接受合法 IPv4 / IPv6，防止非法 Header 或测试客户端名称污染节点地址。

## 修改点

- `backend/app/api/agents.py`
  - 提取合法 `X-Forwarded-For` / `X-Real-IP` / request client host。
- `backend/app/services/agent_service.py`
  - 在心跳处理时写入 `observedRemoteAddress`。
  - 旧 Agent 未上报主机身份时，用观测远端 IP 回填 `server_ip` 和 `reportedAddress`。
- `backend/app/services/project_service.py`
  - 项目发布部署节点地址判断增加 `observedRemoteAddress`。
- `frontend/src/views/ServersPage.vue`
  - 执行节点页地址展示增加 `observedRemoteAddress` 兜底。
- `frontend/src/views/ProjectPublishPage.vue`
  - 发布页部署节点地址展示与可用性判断增加 `observedRemoteAddress`。
- `frontend/src/types/api.ts`
  - AgentMetrics 增加 `observedRemoteAddress` 类型字段。

## 边界

这不是替代 Agent 新版主机身份上报。新版 Agent 仍应优先上报 `hostIp/publicIp/hostname`。该修复只用于兼容旧 Agent 或上报字段暂缺场景。

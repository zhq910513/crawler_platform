# Agent 主机地址自动采集与部署可用判断修复 v1.0.84

## 背景

执行节点通过安装命令接入后，项目发布页可能显示“未上报地址 可部署”。这会造成两个误导：

1. 地址字段没有自动采集，用户需要猜测“上报地址”含义。
2. 未完成首次心跳的节点也可能在前端本地判断中显示为“可部署”。

## 根因

- `crawler_server.server_ip` 是现有节点地址字段，但 Agent 安装脚本与心跳没有稳定回填该字段。
- 复用长期 Agent 凭据时，安装脚本跳过 Join Token 换取配置，之前没有把本次宿主机地址提交给控制端。
- 项目发布页本地 `serverDeployable()` 主要看健康状态、容量状态和 Docker 指标，没有先判断 Agent 是否已首次心跳上线。

## 修复方案

### 安装脚本

安装脚本新增：

- `detect_hostname()`
- `detect_host_ip()`
- `append_host_identity_env()`

采集结果写入：

- `AGENT_HOSTNAME`
- `AGENT_HOST_IP`
- `AGENT_PUBLIC_IP`

Join Token 换取配置时，提交：

- `hostname`
- `hostIp`
- `publicIp`

复用长期 Agent 凭据时，也通过 `resume-env` 查询参数提交上述字段。

### Agent 心跳

Agent 心跳 payload 新增：

- `hostname`
- `hostIp`
- `publicIp`

控制端接收后：

- 如果 `crawler_server.server_ip` 为空，则用 `hostIp / publicIp / hostname` 自动补齐。
- 同步写入 `server.metrics.hostname / hostIp / publicIp / reportedAddress`。

### 项目发布页

部署节点判断新增硬条件：

- 必须存在 Agent。
- `agentConnectionStatus` 必须为 `ONLINE`。
- 必须存在 `agentLastHeartbeatAt`。

未满足时，展示真实阻断原因：

- `待接入`
- `等待首次心跳`
- `离线`

地址展示统一改为：

```text
serverIp -> metrics.reportedAddress -> metrics.hostIp -> metrics.publicIp -> metrics.hostname -> 节点地址采集中
```

## 未改变的契约

- 没有新增数据库列。
- 没有改变原有 `crawler_server.server_ip` 字段含义。
- 没有强制要求公网 IP；默认采集宿主机默认网卡 IP。
- 没有把 Agent 容器内部 IP 当成执行节点地址。

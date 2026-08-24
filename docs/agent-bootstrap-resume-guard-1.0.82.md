# Agent 接入长期凭据复用保护记录 v1.0.82

## 背景

现场执行新增执行节点接入命令时，目标机安装脚本检测到 `/opt/crawler-agent/.env` 中已有长期 Agent 凭据，并直接调用 `resume-env` 复用旧凭据。由于旧凭据不一定属于当前新生成的 Join Token，脚本会跳过本次 Join Token 换取配置，导致新接入记录一直停留在“待接入/接入中”。

## 根因

v1.0.81 安装脚本只校验长期 Agent Token 是否仍被平台认可，没有校验这个旧 Token 对应的 `serverCode/agentCode` 是否等于当前接入命令对应的 `serverCode/agentCode`。

因此目标机上存在旧 `/opt/crawler-agent/.env` 时，可能出现：

```text
新 Join Token 未消费
旧 Agent 配置被复用
新接入记录仍是 PENDING
旧接入记录仍是 CONFIG_ISSUED
控制台持续显示等待首次心跳
```

## 修复

1. 安装脚本复用长期凭据时携带当前 `joinToken`。
2. 控制端根据 `joinToken` 查出目标 `serverCode/agentCode`。
3. 若旧长期凭据所属 Agent 与当前 Join Token 不一致，则拒绝 resume，脚本自动使用本次 Join Token 重新换取配置。
4. 接入配置已下发但超过 5 分钟未收到首轮心跳时，接入记录自动标记为接入失败，避免长期卡在“接入中”。
5. 安装脚本输出当前使用的 `server / agent / image`，便于现场快速判断是否仍在使用旧配置。

## 未改动边界

- 没有修改 Agent 心跳 API 契约。
- 没有修改数据库表结构。
- 没有修改 Agent 镜像版本策略；Agent 版本仍独立于平台版本。
- 没有虚构 Redis、Docker Registry 或远程主机状态。

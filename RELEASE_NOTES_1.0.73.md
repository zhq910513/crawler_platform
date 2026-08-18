# crawler_platform v1.0.74 发布说明

## 版本定位

v1.0.74 是 Agent 生命周期主动审计修复版，针对 v1.0.72 重构后的真实代码链路继续做反向推理，修复“设计承诺已成立但执行链路未完全闭环”的问题。

## 核心修复

1. **长期 Agent Credential 续跑真正落地**
   - 安装器会优先校验本机已存在的长期 Agent Credential。
   - Credential 有效时直接获取平台当前 Agent 目标配置并继续安装，不再重复消费一次性 Join Token。
   - 平台返回的续跑配置不包含原始 Token，安装器只复用本机已有 Token。

2. **Agent 独立版本递增**
   - 平台版本：`1.0.74`。
   - Agent 独立版本：`1.1.2`。
   - 协议版本仍为 `1.0`。
   - Agent 代码发生变化后不允许继续使用 `1.1.0`，避免新代码用旧 Agent 版本号发布。

3. **Drain 后生命周期自动收敛**
   - 节点移除时如果仍有运行任务，会进入 Drain。
   - 任务结束后的后续心跳会自动推进退役命令，不再要求人工再次点击。
   - 如果 Agent 不支持退役或已经不可达，平台撤销长期身份、清理当前节点记录，并生成远端清理未确认告警。

4. **Agent 备份容器清理闭环**
   - 默认智能替换/升级会保留旧 Agent 容器用于回滚。
   - 新 Agent 稳定后自动清理 `crawler-agent-old-*` 已停止备份容器，避免远端垃圾累积。

5. **版本解耦残留清理**
   - Agent 运行版本不再 fallback 到平台 `APP_VERSION` 或仓库根 `VERSION`。
   - Agent Dockerfile 默认版本更新为 `1.1.2`。
   - 单机 compose 默认 Agent 镜像更新为 `crawler_platform_agent:1.1.2`。

## 验收重点

- 平台普通 patch 不触碰 Agent。
- Agent 代码变化必须递增 Agent 独立版本。
- Token 消费后后续失败可用长期 Credential 原地续跑。
- Drain 后退役自动推进。
- 退役后无法确认远端清理时生成 P1 运维告警。
- 旧 Agent 备份容器自动清理。

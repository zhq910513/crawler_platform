# crawler_platform v1.0.110

## 版本定位

本版本不是单点任务编排改动，而是对“项目源码 → 构建 → Release → 节点部署 → 运行前自检 → Release 激活 → Definition → 编排 → 调度/手动运行 → Agent 执行 → 再发布”的完整运行链路做一致性治理。

核心原则：**注册产物不等于运行版本；候选就绪不等于生产已切换；Manifest 只拥有定义事实，用户拥有编排决策；所有运行入口共享同一套可运行性门禁。**

## 核心整改

1. **Release 登记与运行激活分离**：新 Release 注册后不会立即切换 `stable`，也不会提前同步新 Definition 或覆盖节点当前运行版本。
2. **Controlled Rollout**：`maxParallelPulls` 由真实 Agent command queue 执行，同一时间只下发指定数量的候选镜像准备任务，ACK 后释放并发槽位再下发下一目标。
3. **Atomic Activation**：候选镜像拉取和 smoke test 成功只记录到 `crawler_project_deployment_target`；所有选定目标达到激活条件后，才在同一事务内更新 `crawler_project_server`、切换 channel、同步 Definition 并提升项目到 `ONLINE`。
4. **稳定版本保护**：候选 Release 部署失败不会破坏已验证的 stable 运行事实；未参与本次 rollout 的旧版本节点在新 stable 激活后标记为 `OUTDATED`，不会承接新 Release 任务。
5. **任务定义生命周期**：Definition 拆分 `discovery_status` 与 `orchestration_status`，支持 `ACTIVE/REMOVED/INVALID` 与 `PENDING/ORCHESTRATED/IGNORED`，发布同步不得覆盖用户的忽略决策。
6. **发现幂等**：待编排查询除 `PENDING` 外增加正式任务存在性保护，已经编排过的 Definition 不会重复进入发现列表。
7. **忽略/恢复**：待处理 Definition 支持忽略、原因、操作人、时间审计，并可从已忽略区域恢复；忽略状态跨 Release 保留。
8. **Definition 漂移治理**：新 Release 改变入口或运行契约时，已编排任务进入 `NEEDS_REVIEW`；自动计划停止继续触发，管理员可显式“同步定义”后恢复。
9. **统一 Runtime Readiness**：手动运行、任务启用、计划启用、Scheduler 共用同一套 Release / Definition / 数据资源 / 平台账号 / 节点就绪判断。
10. **渐进式编排**：新任务默认可先保存为 `DRAFT`，允许后补资源和账号；进入 `ENABLED` 或实际执行前必须完成所有必需绑定。
11. **节点意图与运行事实分离**：加入项目执行池只代表编排意图，不再伪装成镜像已部署；用户显式指定的执行节点不可偷偷 fallback 到其他节点。
12. **发布助手真实完成语义**：只有节点部署和 smoke test 完成、Release 激活成功后才显示发布成功。

## 数据库迁移

新增 Alembic revision：`0018_definition_lifecycle`。

`crawler_project_task_definition` 新增并迁移：

- `discovery_status`
- `orchestration_status`
- `first_seen_release_id`
- `last_seen_at`
- `ignored_at`
- `ignored_by`
- `ignore_reason`

旧 `definition_status` 会在迁移中转换后删除。

## 关键不变量

```text
Release registered != Release active
Candidate READY != ProjectServer promoted
ProjectServer == 当前正式可承接任务的运行事实
DeploymentTarget == 候选 Release 准备事实
Manifest owns Definition facts
User owns orchestration decisions
Task runnable == active Release + compatible Definition + valid bindings + READY nodes
```

## 回归重点

- 候选 Release 注册不会影响当前 stable 任务和节点。
- `maxParallelPulls=1` 时任意时刻只存在一个候选部署 command；ACK 后才下发下一目标。
- 候选目标未全部成功前 `ProjectServer` 不提前切版本，Definition 不提前暴露。
- 全部目标成功后原子激活，目标节点统一切新 Release。
- `IGNORED` 跨 Release 保留并可恢复。
- Definition 漂移会阻断执行并停止 CRON 重复触发，显式 reconcile 后恢复。
- DRAFT 可缺少必需绑定，启用/执行不可缺少。
- 显式节点目标不可 fallback。

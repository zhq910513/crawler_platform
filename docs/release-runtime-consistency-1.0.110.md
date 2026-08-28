# Release-to-Runtime 一致性设计（v1.0.110）

## 目标

平台任何“成功、可用、可执行”的状态都必须对应真实运行事实，避免构建、Release、节点、Definition、任务、计划之间各自维护互相矛盾的状态。

## 状态所有权

- `CrawlerProjectRelease`：不可变发布产物事实。
- `CrawlerProjectDeploymentTarget`：候选 Release 在某节点上的准备与 smoke test 事实。
- `CrawlerProjectServer`：某节点当前正式可承接生产任务的运行事实。
- `CrawlerReleaseChannel`：当前激活运行版本。
- `CrawlerProjectTaskDefinition`：Manifest 提供的能力事实 + 用户编排决策。
- `CrawlerTask`：正式业务编排实例。

## 发布状态机

```text
PUBLISHED Release
  -> Deployment targets created
  -> maxParallelPulls controlled dispatch
  -> candidate pull + smoke test
  -> all selected targets READY
  -> activation barrier
  -> atomically promote ProjectServer
  -> switch stable channel
  -> sync task definitions
  -> project ONLINE
```

候选失败时 stable channel 和已有 `ProjectServer` 运行事实保持不变。

## Definition 状态机

```text
discovery_status: ACTIVE | REMOVED | INVALID
orchestration_status: PENDING | ORCHESTRATED | IGNORED
```

Manifest 同步只能更新发现事实和 Definition 内容，不得覆盖 `IGNORED` 等用户决策。

## Runtime Readiness

统一检查：

1. 项目已 `ONLINE`；
2. stable channel 存在有效 Release；
3. Definition 仍为 ACTIVE 且已编排；
4. task contract snapshot 与最新 Definition 兼容；
5. requiredConfigs / requiredCredentials 已完成有效绑定；
6. 满足 requiredNodeCount 的节点处于当前 Release + DEPLOYED + READY；
7. 显式节点目标必须满足条件，不允许隐式 fallback。

手动运行、任务启用、计划启用和 Scheduler 必须共享该判断。

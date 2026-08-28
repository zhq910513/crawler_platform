# crawler_platform v1.0.109

## 版本定位

本版本修复“项目发布成功后任务定义已经被平台发现，但任务编排页面没有展示”的产品链路断点。

## 核心修复

1. `task-schedule-panels` 在正式任务列表之外返回 `pendingDefinitions` / `pendingDefinitionTotal`。
2. 待编排定义直接来自 `crawler_project_task_definition`，仅展示 `AVAILABLE` 状态，不伪造 `crawler_task`。
3. 任务编排页面新增“自动发现待编排任务”区域，发布成功后可直接看到 manifest 中尚未编排的任务。
4. “开始编排”复用现有正式任务创建流程并自动定位公司、项目和 definition。
5. 正式任务创建后 definition 状态变为 `CREATED`，自动从待编排区域消失并进入正式任务列表。
6. 不自动创建/启用正式任务，避免绕过数据库配置、平台账号、执行节点和计划绑定契约。

## 数据模型

无数据库迁移。现有职责保持不变：

```text
manifest.taskDefinitions
  -> crawler_project_task_definition (自动发现)
  -> 任务编排 / pendingDefinitions (待人工完成绑定)
  -> crawler_task + crawler_task_schedule (正式任务)
```

## 回归重点

- 项目接入后、正式任务创建前，任务编排接口必须返回待编排定义。
- 正式任务创建后，待编排数量归零，对应正式任务进入列表。
- 原正式任务分页、运行、调度和删除契约保持不变。

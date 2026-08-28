# 任务自动发现到任务编排闭环（v1.0.109）

## 问题

平台构建中心已经从爬虫项目 manifest 读取 `taskDefinitions`，`ProjectService._sync_task_definitions()` 也会写入 `crawler_project_task_definition`。但任务编排页原来只查询 `crawler_task`，导致发布完成后用户看不到已经发现但尚未创建正式任务的定义。

## 修复后的职责

- `crawler_project_task_definition`：代码侧自动发现事实。
- `crawler_task`：用户完成配置/账号/计划等绑定后的正式可运行任务。
- `/task-schedule-panels`：同时返回正式任务 `items` 与待编排定义 `pendingDefinitions`。

平台不会把 definition 自动转换成启用任务，因为任务契约可能要求 `requiredConfigs` / `requiredCredentials`。发现与运行继续保持两阶段模型。

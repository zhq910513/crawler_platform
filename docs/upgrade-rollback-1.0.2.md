# crawler_platform 1.0.1 -> 1.0.2 升级与回滚说明

## 升级范围

1.0.2 增加账号密码安全、多时间点调度、Agent 资源状态、日志 V2 基础表和商业发布门禁。

数据库迁移：

- `0002_platform_1_0_2_observability.py`：新增密码字段、运行日志字段、运行事件表、日志分片表。
- `0003_expand_schedule_cron_expression.py`：将 `crawler_task_schedule.cron_expression` 扩展到 1000 字符，用于保存业务多时间点组合表达式。

## 升级前检查

- 备份 MySQL 数据库。
- 记录当前镜像 tag 和 digest。
- 记录当前 `.env` 脱敏副本。
- 确认 admin 账号可登录。
- 确认所有正在运行任务状态，必要时暂停调度窗口。

## 升级后检查

- `/health` 返回 `version=1.0.2`。
- Alembic head 为 `0003_expand_schedule_cron_expression`。
- admin 用户仍可登录。
- 已有公司、Agent、项目、任务和历史运行记录可查看。
- 新建普通用户首次登录要求改密。
- Agent 心跳资源字段在服务器列表可见。
- 日志 V2 接口可查询 events、log-tails、diagnoses、log-downloads。
- 每日/每周/每月多时间点可预览未来 5 次。

## 回滚策略

- 支持代码和镜像回滚。
- 数据库迁移包含 downgrade，但商业生产环境若已经写入 1.0.2 日志数据，不建议直接降级；优先使用升级前数据库备份恢复。
- 若仅代码回滚到 1.0.1，新表和新增字段不会被旧代码使用，但应保留备份以便二次升级。

## Breaking Changes

- 无强制 API 删除。
- 当前用户修改密码新增规范路径：`PATCH /api/v1/users/me/password`。
- 为兼容旧前端，保留 `PATCH /api/v1/users/current/passwords`。
- 多时间点调度的 `cronExpression` 可能为分号连接的多个 5 段 Cron；调度器和预览接口已内置支持，不应由外部 Cron 解析器直接消费。

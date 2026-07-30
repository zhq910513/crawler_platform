# V2 数据库核心表

## 系统域

- `sys_user`：平台登录用户。
- `sys_login_log`：登录记录。
- `sys_operation_log`：操作审计。
- `sys_config`：普通配置。
- `sys_secret`：加密密钥，密文保存。

## 多租户域

- `crawler_company`：公司或租户。
- `crawler_company_member`：公司成员与角色。
- `crawler_project`：公司下的项目。
- `crawler_project_member`：项目成员与 `OWNER/OPERATOR/VIEWER` 权限。

## 发布域

- `crawler_spider_release`：不可变爬虫发布版本，包含版本、Git Commit、镜像摘要和 manifest。
- `crawler_spider_entry`：发布中可执行的 SpiderEntry，例如 `system.health`、`baidu.shop_detail`。
- `crawler_release_channel`：项目通道，例如 stable、canary，绑定 SpiderRelease。

旧 `crawler_image_version` 仅保留兼容，不再作为 V2 任务的首选执行源。

## 资源域

- `crawler_resource_connection`：MySQL、MongoDB、Redis 物理连接配置。
- `crawler_resource_database`：连接下的逻辑数据库。
- `crawler_resource_object`：逻辑表或 Collection。
- `crawler_project_resource_binding`：项目逻辑资源名到真实资源对象的绑定。
- `crawler_project_secret_binding`：项目逻辑密钥名到加密密钥的绑定。

资源按公司和项目隔离。任务运行时只下发当前 SpiderEntry 声明且项目已绑定的最小资源集合。

## Agent 域

- `crawler_server`：爬虫服务器静态信息。
- `crawler_agent`：Agent 身份、协议版本、实例 ID、能力、标签和心跳。
- `crawler_server_metric`：服务器性能历史。

## 任务域

- `crawler_task`：任务定义，绑定 `spider_task_name`。
- `crawler_task_runtime`：发布策略、资源限制和容器约束。
- `crawler_task_schedule`：Cron、超时、重试和并发策略。
- `crawler_task_target`：允许执行的服务器或 Agent 目标。
- `crawler_task_run`：每次执行实例，包含租约、状态、last_error、terminal_error、result 和 metrics。
- `crawler_task_run_event`：结构化运行事件，按 `run_id + event_uid` 幂等。
- `crawler_container_event`：容器生命周期事件。

## 状态机

```text
CREATED
QUEUED
ASSIGNED
STARTING
RUNNING
CANCEL_REQUESTED
SUCCEEDED
PARTIAL_SUCCESS
SKIPPED
FAILED
CANCELLED
TIMED_OUT
LOST
```

终态不可回退。失败重试创建新的 TaskRun，通过 `root_run_id/parent_run_id/attempt` 串联。

## 迁移

数据库结构由 Alembic 管理。Compose 中 `migrate` 服务会在 API/Scheduler/Maintenance 启动前执行迁移。生产回滚以数据库备份为准，不提供破坏性自动 downgrade。

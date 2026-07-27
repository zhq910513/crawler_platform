# 数据库核心表

## 系统域

- `sys_user`：平台用户，仅两种角色。
- `sys_login_log`：登录记录。
- `sys_operation_log`：任务操作审计。
- `sys_config`：普通配置。
- `sys_secret`：加密密钥。

## 执行节点域

- `crawler_server`：爬虫服务器静态信息。
- `crawler_agent`：Agent 身份和心跳。
- `crawler_server_metric`：服务器性能历史。

## 镜像域

- `crawler_project`：爬虫项目与镜像仓库。
- `crawler_image_version`：CI/CD 构建镜像摘要。
- `crawler_release_channel`：stable、staging 等通道。

## 任务域

- `crawler_task`：任务基本定义。
- `crawler_task_runtime`：容器运行参数。
- `crawler_task_schedule`：Cron、重试、并发和超时。
- `crawler_task_target`：任务允许执行的服务器。
- `crawler_task_run`：每次执行实例，是平台核心表。
- `crawler_container_event`：Docker 生命周期事件。

完整表结构由 SQLAlchemy 模型定义，API 启动时自动创建。正式长期迭代时建议接入 Alembic 管理数据库迁移。

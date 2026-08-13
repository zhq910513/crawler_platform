# crawler_platform 1.0.21 发布说明

## 修复目标

修复 1.0.20 在真实 MySQL 迁移中仍然失败的问题：`crawler_project_deployment_target.last_error` 为 `TEXT` 类型却设置了 `server_default=""`，MySQL 不允许 `TEXT/BLOB/JSON/GEOMETRY` 字段设置默认值。

## 修复内容

- 移除 `0006_agent_deploy.py` 中 `last_error TEXT NOT NULL DEFAULT ''` 的默认值。
- 强化 `deploy/scripts/check-mysql-json-defaults.py`，不再只检查 JSON，改为检查 JSON / TEXT / BLOB / LargeBinary 等 MySQL 禁止默认值的列类型。
- 发布门禁继续执行该检查，避免后续迁移文件再次引入同类问题。
- 版本统一递增到 1.0.21。

## 影响范围

- 只修改 crawler_platform。
- crawler_platform_spiders 不变，继续使用 1.0.12。
- 数据库迁移 head 不变，仍为 `0009_contract_runtime_gate`。

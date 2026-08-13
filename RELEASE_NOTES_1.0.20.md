# crawler_platform 1.0.20 发布说明

## 修复

- 修复 MySQL 生产升级失败：JSON 列不能带 `server_default`，导致 `0006_agent_deploy` 在 `crawler_server.labels` 上执行 `ALTER TABLE ... JSON NOT NULL DEFAULT '{}'` 失败。
- 重写 0006 / 0008 迁移中新增 JSON 列的方式：先 nullable 添加、回填 `{}` 或 `[]`，再在非 SQLite 方言上收紧为 NOT NULL。
- 移除 0006 / 0007 / 0008 / 0009 新建表中 JSON 列的 server_default，避免 MySQL 1101 错误。
- 商业发布门禁新增 `check-mysql-json-defaults.py`，静态阻断后续 JSON/TEXT/BLOB 默认值兼容问题。

## 影响范围

- 仅影响 crawler_platform 数据库迁移与发布门禁。
- crawler_platform_spiders 1.0.12 无需变更，继续作为当前爬虫基础包。

## 升级说明

- 适用于 1.0.19 在 MySQL/CentOS 生产环境迁移到 0006 时失败后的重试。
- 失败发生在 `ALTER TABLE crawler_server ADD COLUMN labels JSON NOT NULL DEFAULT '{}'`，通常不会写入该列；新版本迁移具备列存在判断，可安全重试。

# 平台构建中心 MySQL 迁移兼容修复 1.0.93

## 背景

商业发布门禁在 MySQL JSON/TEXT/BLOB 默认值兼容检查阶段发现：

```text
backend/migrations/versions/0017_project_build_center.py
sa.Column("error_message", sa.Text(), nullable=False, server_default="")
```

MySQL 不允许 JSON/TEXT/BLOB 等 LOB 类型字段使用 server_default。

## 修复

`crawler_project_build_job.error_message` 保持应用层默认空字符串，但迁移层移除 `server_default`：

```python
sa.Column("error_message", sa.Text(), nullable=False)
```

这不改变现有服务层写入契约。ORM 模型仍负责在应用层提供默认值，构建失败时服务层会显式写入错误信息。

## 不做的事

- 不修改 `CrawlerProjectBuildJob` 模型字段语义。
- 不改构建中心状态机。
- 不改项目发布主链路。
- 不引入新的数据库字段。

## 验证点

- 迁移文件中 `Text` 字段不再带 `server_default`。
- 构建中心核心测试继续通过。
- 版本与发布文件同步到 1.0.93。

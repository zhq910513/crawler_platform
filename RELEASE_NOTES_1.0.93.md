# RELEASE_NOTES 1.0.93

## 变更摘要

- 修复 `0017_project_build_center.py` 中 `error_message` Text 字段使用 `server_default=""` 导致 MySQL 兼容门禁失败的问题。
- 保持 `CrawlerProjectBuildJob.error_message` 的应用层默认值不变，只移除数据库层 LOB 默认值。
- 新增迁移兼容性防回归测试，避免后续再次在构建中心迁移里为 Text 字段添加 MySQL 不允许的 server_default。

## 验证

- Python compileall：通过。
- Shell bash -n：通过。
- 构建中心 MySQL 兼容防回归测试：通过。
- 构建中心最小发布闭环测试：通过。
- 版本一致性：1.0.93。

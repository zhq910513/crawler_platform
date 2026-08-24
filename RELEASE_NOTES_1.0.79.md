# crawler_platform v1.0.79 发布说明

## 发布定位

v1.0.79 是 v1.0.78 运行契约修复后的上线候选整改版，重点解决发布包清洁度、版本一致性和上线前自动化检查问题。

## 变更内容

- 删除发布包中的本地开发数据库 `crawler_platform_dev.db`。
- `.gitignore` 增加本地 SQLite/DB 文件排除规则。
- 同步平台版本到 `1.0.79`：`VERSION`、`.env.example`、`docker-compose.yml`、前端 package 文件、部署脚本兜底版本。
- 新增 `backend/tests/test_release_package_hygiene_1079.py`，覆盖：
  - 发布源码目录不得包含 `*.db` / `*.sqlite` / `*.sqlite3`。
  - `.gitignore` 必须排除本地数据库文件。
  - `.env.example` 与 `docker-compose.yml` 默认发布版本必须等于根目录 `VERSION`。
  - 前端 package 版本必须等于根目录 `VERSION`。
- 新增 `docs/production-readiness-audit-1.0.79.md`，记录上线候选包审计结论和真实环境待验证清单。

## 测试

本版本应至少通过：

```bash
python -m compileall -q backend/app agent/crawler_agent runtime/crawler_runtime backend/tests
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests
```

前端构建、Docker Compose、MySQL、Redis、Agent、真实爬虫镜像执行仍需在具备完整依赖和外部服务的测试服或准生产环境验证。

## 上线建议

v1.0.79 可以作为测试服 / 准生产联调候选包。只有真实 Agent + Docker + 爬虫镜像端到端链路通过后，才建议进入生产发布。

# crawler_platform v1.0.80 发布说明

v1.0.80 是在 v1.0.79 上线候选包基础上的 CI 修复版，重点处理商业发布门禁暴露的后端发布包卫生失败和前端 TypeScript 构建失败。

## 修复内容

1. 保持发布包不包含本地开发数据库文件，并继续通过发布包卫生测试阻断 `*.db` / `*.sqlite` / `*.sqlite3` 入包。
2. 将平台版本统一提升到 `1.0.80`：`VERSION`、`.env.example`、`docker-compose.yml`、前端 package 文件、部署脚本和测试断言同步更新。
3. 修复 `frontend/src/views/CompanyResourcesPage.vue` 中模板引用 `testStatusOptions` 但脚本未定义的问题。
4. 新增 `backend/tests/test_frontend_company_resources_contract_1080.py`，防止数据资源页面测试状态筛选项再次缺失。
5. 新增 `docs/ci-failure-review-1.0.80.md` 和 `docs/release-verification-1.0.80.md`，记录 CI 失败原因、整改边界和本地验证结果。

## 上线结论

v1.0.80 可作为 v1.0.79 的 CI 修复候选包继续进入商业发布门禁。生产发布前仍需以 GitHub Actions / 测试服结果为最终准入依据，并继续完成真实 Agent + Docker + spider image 端到端联调。

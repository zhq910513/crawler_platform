# v1.0.80 发布候选包验证记录

## 验证目标

本轮验证重点针对 CI 暴露的两个阻断项：

1. 发布树不能包含本地数据库文件。
2. 前端 `CompanyResourcesPage.vue` 必须通过模板变量契约检查，避免 `vue-tsc` 报 `testStatusOptions` 不存在。

## 已执行校验

- Python 语法编译。
- 后端发布包卫生测试。
- 前端数据资源页面契约测试。
- 后端文件级测试集合。
- 版本一致性检查。
- ZIP 解压后 manifest 与源码 manifest 对比。
- ZIP 解压后 `*.db` / `*.sqlite` / `*.sqlite3` 检查。

## 仍需外部环境确认

当前容器不具备完整 Docker 发布环境和真实 Agent / spider image 联调条件。生产上线前仍需在 CI 或测试服执行完整商业发布门禁、前端 Docker 镜像构建、Agent 认领任务、任务容器运行、日志回传、结果回传和账号凭据租约链路。


## 本地验证结果

本轮在交付前完成以下校验：

```bash
python -m compileall -q backend/app agent/crawler_agent runtime/crawler_runtime backend/tests deploy/scripts/check-alembic-graph.py
bash -n deploy/scripts/commercial-release-gate.sh
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_release_package_hygiene_1079.py tests/test_frontend_company_resources_contract_1080.py tests/test_runtime_binding_injection_1078.py tests/test_rebuild_contract.py
cp .env.example .env && bash deploy/scripts/check-version-consistency.sh && rm -f .env
```

结果：核心发布卫生、前端页面契约、运行绑定注入和重建契约测试共 `71 passed`。版本一致性检查通过：`releaseVersion=1.0.80`，`warnings=0`。

当前容器中 `frontend npm ci` 仍受依赖下载环境影响未完成，因此本地没有声明前端完整 `npm run build` 通过。CI 日志中依赖安装阶段已经成功，阻断点是 `CompanyResourcesPage.vue` 的 `testStatusOptions` 未定义；本轮已针对该真实文件完成修复并新增契约测试。

# v1.0.84 发布候选包验证记录

## 检查项

```bash
python -m compileall -q backend/app agent/crawler_agent runtime/crawler_runtime backend/tests deploy/scripts/check-alembic-graph.py
bash -n backend/app/templates/install-agent.sh deploy/scripts/commercial-release-gate.sh deploy/scripts/deploy-single-server.sh
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_agent_host_identity_1084.py tests/test_frontend_refresh_navigation_1083.py tests/test_agent_onboarding_ui_1081.py tests/test_frontend_company_resources_contract_1080.py tests/test_release_package_hygiene_1079.py tests/test_rebuild_contract.py
cp .env.example .env && bash deploy/scripts/check-version-consistency.sh && rm -f .env
```

## 结果

- 编译检查：通过。
- Shell 检查：通过。
- 关键测试：`84 passed`。
- 版本一致性：`releaseVersion=1.0.84`，`warnings=0`。

## 仍需生产环境验证

- GitHub Actions 前端镜像构建。
- 真实执行节点重新生成接入命令后完成首次心跳。
- 真实爬虫镜像发布、部署、任务执行、日志和结果回传。

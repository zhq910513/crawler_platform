# v1.0.85 发布校验记录

## 版本

```text
1.0.85
```

## 校验项

```bash
python -m compileall -q backend/app agent/crawler_agent runtime/crawler_runtime backend/tests deploy/scripts/check-alembic-graph.py
bash -n backend/app/templates/install-agent.sh deploy/scripts/commercial-release-gate.sh deploy/scripts/deploy-single-server.sh
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_agent_transient_control_plane_errors_1085.py tests/test_agent_host_identity_1084.py tests/test_frontend_refresh_navigation_1083.py tests/test_rebuild_contract.py
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_release_package_hygiene_1079.py tests/test_agent_bootstrap_resume_guard_1082.py tests/test_agent_onboarding_ui_1081.py tests/test_runtime_binding_injection_1078.py tests/test_frontend_company_resources_contract_1080.py
cp .env.example .env && bash deploy/scripts/check-version-consistency.sh && rm -f .env
```

## 结果

```text
Python 编译检查：通过
Shell bash -n：通过
核心回归测试：91 passed
版本一致性：releaseVersion=1.0.85 warnings=0
ZIP 解压 manifest：通过
```

## 发布包卫生

```text
无 *.db / *.sqlite / *.sqlite3
无 node_modules / dist / __pycache__ / .pytest_cache
源码目录与 ZIP 解压目录 sha256 manifest 一致
```

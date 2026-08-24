# v1.0.81 发布候选包验证记录

## 编译检查

```bash
python -m compileall -q backend/app agent/crawler_agent runtime/crawler_runtime backend/tests deploy/scripts/check-alembic-graph.py
```

结果：通过。

## 后端契约测试

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q \
  tests/test_agent_onboarding_ui_1081.py \
  tests/test_release_package_hygiene_1079.py \
  tests/test_frontend_company_resources_contract_1080.py \
  tests/test_runtime_binding_injection_1078.py \
  tests/test_rebuild_contract.py
```

结果：`75 passed`。

## 版本一致性

```bash
cp .env.example .env
bash deploy/scripts/check-version-consistency.sh
rm -f .env
```

结果：通过，`releaseVersion=1.0.81`，`warnings=0`。

## 前端构建说明

当前执行环境 `npm ci` 超时，未完成本地 `npm run build`。本次新增的是静态 UI 交互契约测试，正式合入后仍需以 GitHub Actions / 测试服的前端镜像构建结果作为准入依据。

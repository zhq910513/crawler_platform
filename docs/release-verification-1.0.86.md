# v1.0.86 发布校验记录

## 校验范围

本轮仅针对 `crawler_platform` 平台仓库，目标是补齐公司资源配置运行时解析与下发链路。

## 已执行命令

```bash
python -m compileall -q backend/app agent/crawler_agent runtime/crawler_runtime backend/tests deploy/scripts/check-alembic-graph.py
bash -n backend/app/templates/install-agent.sh deploy/scripts/commercial-release-gate.sh deploy/scripts/deploy-single-server.sh
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_runtime_resource_resolution_1086.py tests/test_runtime_binding_injection_1078.py tests/test_task_contract_1018.py tests/test_company_resource_pool_1077.py tests/test_release_package_hygiene_1079.py tests/test_agent_transient_control_plane_errors_1085.py tests/test_agent_host_identity_1084.py tests/test_frontend_refresh_navigation_1083.py
cp .env.example .env && bash deploy/scripts/check-version-consistency.sh && rm -f .env
```

## 结果

```text
Python compileall：通过
Shell bash -n：通过
核心回归测试：25 passed
版本一致性检查：releaseVersion=1.0.86 warnings=0
```

## 交付包校验项

打包前需确认：

```text
源码目录代码 = ZIP 解压后代码
sha256 manifest 一致
无 *.db / *.sqlite / *.sqlite3
无 node_modules / dist / __pycache__ / .pytest_cache
关键发布文件无旧版本默认值残留
Run Snapshot 不包含明文资源配置
Agent claim payload 包含 configs/runtimeConfigs
DockerRunner 注入 CRAWLER_CONFIG_JSON.configs
```

## 仍需真实环境验证

- GitHub Actions 前端镜像构建。
- 真实 Agent + Docker + spider image 端到端部署。
- 真实公司资源配置绑定后运行 JDD 测试任务。

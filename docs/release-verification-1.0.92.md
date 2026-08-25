# v1.0.92 交付校验记录

## 校验范围

仓库：`crawler_platform`
版本：`1.0.92`
主题：平台构建中心最小发布闭环

## 已执行

```bash
python -m compileall -q backend/app agent/crawler_agent runtime/crawler_runtime backend/tests deploy/scripts/check-alembic-graph.py
bash -n backend/app/templates/install-agent.sh deploy/scripts/commercial-release-gate.sh deploy/scripts/deploy-single-server.sh
python deploy/scripts/host-compat-scan.py
python deploy/scripts/commercial-contract-scan.py
python deploy/scripts/check-agent-onboarding-contract.py
python deploy/scripts/check-alembic-graph.py
cp .env.example .env && bash deploy/scripts/check-version-consistency.sh && rm -f .env
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_platform_build_center_minimal_1092.py tests/test_project_publish_platform_build_gate_1088.py tests/test_project_publish_external_release_gate_1087.py tests/test_project_publish_server_address_gate_1090.py tests/test_agent_observed_remote_address_1091.py tests/test_runtime_resource_resolution_1086.py tests/test_alembic_graph_integrity.py
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_rebuild_contract.py
```

## 结果

- 编译检查：通过。
- Shell `bash -n`：通过。
- 商业契约扫描：通过。
- 宿主机兼容扫描：通过。
- 执行节点接入契约检查：通过。
- Alembic 图检查：通过，唯一 head=`0017_project_build_center`。
- 版本一致性：`releaseVersion=1.0.92 warnings=0`。
- 构建中心/发布链路核心测试：`22 passed`。
- 重建契约测试：`65 passed`。

## 未执行

当前容器没有 `docker` 命令，不能在本地执行真实 Docker 镜像构建、push、前端 Docker build 或爬虫项目镜像构建。v1.0.92 的真实构建闭环仍需在具备 Docker、git 和 registry 权限的部署环境验证。

## 发布风险

默认配置仍关闭构建中心。生产启用前必须确认：

```env
CRAWLER_PROJECT_BUILD_ENABLED=1
CRAWLER_PROJECT_IMAGE_REPOSITORY_PREFIX=...
```

并确保构建执行环境已经安全配置代码仓库读取权限和镜像仓库推送权限。

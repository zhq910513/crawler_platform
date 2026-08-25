# Release Notes v1.0.86

## 版本定位

本版本补齐公司资源配置在运行时的解析与下发链路，修正“任务只拿到 configBindings 引用，业务爬虫无法通过 context.config 读取真实公司配置”的平台侧缺口。

## 核心变更

- 新增 `RuntimeResourceResolver`：在 Agent claim run 时按公司、项目和任务绑定解析 `CompanyResourceConfig`。
- Run 快照仍只保存 `configBindings` / `credentialBindings` 引用，不把数据库、Redis、Mongo、OSS 等明文连接配置写入 `CrawlerTaskRun.parameters_snapshot`。
- Agent claim response 新增 `configs` / `runtimeConfigs`，仅在执行节点领取任务时下发本次 Run 被授权使用的最小配置。
- DockerRunner 注入 `CRAWLER_CONFIG_JSON` 时同时带上：
  - `configs`
  - `config`
  - `configBindings`
  - `config_bindings`
- 必需配置声明的资源类型会在运行时解析阶段校验，例如 `MONGO` 映射到 `MONGODB`。
- 对象式资源绑定在任务保存阶段做轻量校验，旧字符串引用格式保持兼容，不改变既有 API 用法。

## 安全边界

- 未新增数据库字段。
- 未修改资源配置加密存储结构。
- 未虚构 Mongo/MySQL/Redis/OSS 客户端。
- 未让业务代码读取平台数据库。
- 未把明文连接配置写入 Run Snapshot。

## 测试

已执行：

```bash
python -m compileall -q backend/app agent/crawler_agent runtime/crawler_runtime backend/tests deploy/scripts/check-alembic-graph.py
bash -n backend/app/templates/install-agent.sh deploy/scripts/commercial-release-gate.sh deploy/scripts/deploy-single-server.sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_runtime_resource_resolution_1086.py tests/test_runtime_binding_injection_1078.py tests/test_task_contract_1018.py tests/test_company_resource_pool_1077.py tests/test_release_package_hygiene_1079.py tests/test_agent_transient_control_plane_errors_1085.py tests/test_agent_host_identity_1084.py tests/test_frontend_refresh_navigation_1083.py
```

结果：`25 passed`。

版本一致性检查通过：`releaseVersion=1.0.86 warnings=0`。

## 未完成项

- 当前版本只补平台运行时配置解析链路。
- 爬虫项目中的 JDD 小案例需要后续 v1.0.15 按固定平台目录结构重做，删除任务参数里的 `mongoUri` / `mongoConfig` 临时入口。
- 前端镜像构建与真实 Agent + Docker + spider image 端到端部署仍需在 CI / 服务器环境验证。

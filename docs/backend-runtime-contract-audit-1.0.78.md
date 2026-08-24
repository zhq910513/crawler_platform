# 爬虫平台后端运行契约审计与整改记录 v1.0.78

日期：2026-08-24  
范围：`crawler_platform-main` 平台仓库。`crawler_platform_spiders-main` 仅作为运行时契约参照，本轮未修改爬虫业务项目。

## 一、审计结论

平台主链路已经具备“任务定义 → 运行实例 → Agent 认领 → Docker 独立任务容器 → crawler_runtime 执行”的基础闭环，但 v1.0.77 存在一个会直接影响正式任务可运行性的运行契约断点：

- 正式任务保存了 `config_bindings` / `credential_bindings`。
- 创建运行实例时只快照了 `task.parameters + manual parameters`。
- Agent 认领时只把 `parameters_snapshot` 传给执行容器。
- 爬虫项目运行时的 `TaskContext.from_env()` 依赖 `configBindings/config_bindings` 和 `accounts` 构造 `context.config` / `context.accounts`。

因此，在任务已绑定公司级资源配置和账号凭据的情况下，执行容器仍可能拿不到 `context.config` 和 `context.accounts`，导致平台侧配置绑定与爬虫运行时脱节。

## 二、已确认问题记录

### P0：正式任务绑定未进入运行时参数快照

**位置**：

- `backend/app/services/run_service.py`
- `backend/app/services/agent_service.py`
- `agent/crawler_agent/docker_runner.py`

**现象**：

`CrawlerTask.config_bindings` 与 `CrawlerTask.credential_bindings` 是正式任务契约字段，但原运行实例只保存业务参数；Agent 和任务容器只能看到 `parameters`，无法稳定看到配置绑定和账号槽位。

**影响**：

- 爬虫项目中 `context.config.mysql(...)`、`context.config.get(...)` 可能拿不到平台绑定资源。
- 爬虫项目中 `context.accounts.get(...)` 可能拿不到账号槽位。
- 平台“配置绑定/账号绑定”页面即使保存成功，也不等于任务运行时可用。

**整改状态**：已修复。

### P1：账号状态上报与凭据租约端点未传入任务容器

**位置**：

- `agent/crawler_agent/docker_runner.py`

**现象**：

爬虫项目基础库已支持通过环境变量读取账号状态上报端点、租约获取端点、租约释放端点和 Agent 身份，但原任务容器环境变量未注入这些端点。

**影响**：

- `context.accounts.report_*` 可能无法向平台回传账号状态。
- `context.accounts.lease(...)` 可能无法走平台租约链路。
- 多任务共享账号时，平台难以正确感知账号使用状态。

**整改状态**：已修复。基于现有真实 API 路径注入：

- `/api/v1/agent-account-status-events`
- `/api/v1/agent-credential-leases/acquire`
- `/api/v1/agent-credential-leases/release`

### P1：历史运行实例存在旧快照兼容风险

**位置**：

- `backend/app/services/agent_service.py`

**现象**：

升级前已经创建但尚未被 Agent 认领的运行实例，`parameters_snapshot` 可能仍是不完整的旧格式。

**影响**：

升级后旧排队任务仍可能缺少 `accounts` / `configBindings`。

**整改状态**：已修复。Agent 认领时增加一次轻量自愈：如快照缺少运行契约字段，则用任务真实保存的绑定补齐后再下发。

### P2：当前任务容器复用 Agent Token，存在权限收敛空间

**位置**：

- `agent/crawler_agent/docker_runner.py`

**现象**：

为保持现有后端 Agent 鉴权契约，本轮把 `Agent {agent_token}` 注入任务容器用于账号状态上报和租约端点访问。

**影响**：

功能可用，但从权限最小化角度看，任务容器不应长期持有完整 Agent Token。更理想方案是控制面签发“单次运行/短 TTL/限定端点”的 runtime token。

**整改状态**：已记录，不在本轮强改。原因：需要新增后端鉴权模型、token 签发与校验契约，不能在缺少完整安全设计时用伪字段替代。

### P2：完整 pytest 一次性运行存在卡住风险

**位置**：

- `backend/tests/test_rebuild_contract.py`
- `backend/app/services/system_config_service.py`

**现象**：

在当前容器环境中，后端完整 `python -m pytest -q` 一次性运行到约 60 个用例后未返回；拆分按文件执行全部目标用例均可通过。卡住点出现在控制面 preflight/Agent 接入相关测试附近，该区域包含对 registry / url / host:port 的探测逻辑。

**影响**：

上线前 CI 如采用“一次性全量 pytest”可能偶发卡住，建议后续将外部探测完全 mock 化，或为 preflight 测试增加更严格的超时与隔离。

**整改状态**：已记录，本轮未强改。原因：当前无法确认测试服/生产环境对 preflight 的真实外部探测要求，直接裁剪探测逻辑可能把真实上线检查改坏。

## 三、本轮已实施整改

### 1. 统一构造运行时参数快照

新增 `build_runtime_parameters(task, parameters)`：

- 保留任务默认业务参数。
- 合并手动运行参数。
- 注入正式任务保存的 `config_bindings`。
- 注入正式任务保存的 `credential_bindings`。
- 同时兼容 crawler foundation 已支持的命名：
  - `configBindings`
  - `config_bindings`
  - `credentialBindings`
  - `credential_bindings`
  - `accounts`

该函数只传递平台已经保存的绑定引用，不解析真实数据库、Redis、OSS、账号密钥，不新增未知客户端对象。

### 2. RunService 创建运行实例时写入完整快照

单实例任务与分片父任务均改为使用 `build_runtime_parameters(...)`，确保运行实例从创建时即具备完整运行契约。

### 3. AgentService 认领任务时返回显式契约字段

Agent 认领返回中增加：

- `configBindings`
- `credentialBindings`
- `accounts`

并保留完整 `parameters`，降低 Agent 与任务容器对隐式嵌套字段的耦合。

### 4. DockerRunner 注入任务容器运行时环境

任务容器环境增加：

- `CRAWLER_CONFIG_JSON`
- `CRAWLER_AGENT_CODE`
- `CRAWLER_ACCOUNT_STATUS_ENDPOINT`
- `CRAWLER_ACCOUNT_STATUS_TOKEN`
- `CRAWLER_CREDENTIAL_LEASE_ACQUIRE_ENDPOINT`
- `CRAWLER_CREDENTIAL_LEASE_RELEASE_ENDPOINT`

这些变量均来自现有 Agent 配置和真实后端 API 路径，没有新增未确认配置项。

### 5. 新增运行契约回归测试

新增：

- `backend/tests/test_runtime_binding_injection_1078.py`

覆盖：

- 正式任务绑定覆盖运行时保留字段，避免手动参数伪造 `accounts/configBindings`。
- `RunService.create_run()` 快照包含配置绑定和账号槽位。
- `AgentService.claim_run()` 下发 payload 包含 `parameters/configBindings/accounts`。

## 四、上线前测试记录

### 已通过

```bash
python -m compileall -q backend/app agent/crawler_agent runtime/crawler_runtime backend/tests
```

结果：通过。

```bash
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q \
  tests/test_runtime_binding_injection_1078.py \
  tests/test_task_contract_1018.py \
  tests/test_release_gate_1019.py \
  tests/test_account_subject_binding_contract.py \
  tests/test_company_resource_pool_1077.py
```

结果：`11 passed`。

```bash
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q \
  tests/test_release_version_scripts.py \
  tests/test_rebuild_contract.py
```

结果：`72 passed`。

按文件拆分执行的后端测试结果：

- `tests/test_account_status_standard.py`：通过
- `tests/test_account_subject_binding_contract.py`：通过
- `tests/test_alembic_graph_integrity.py`：通过
- `tests/test_cicd_one_click_1030.py`：通过
- `tests/test_company_resource_pool_1077.py`：通过
- `tests/test_company_tenant_isolation_1026.py`：通过
- `tests/test_migration_observability_recovery.py`：通过
- `tests/test_rebuild_contract.py`：通过
- `tests/test_release_gate_1019.py`：通过
- `tests/test_release_version_scripts.py`：通过
- `tests/test_running_center_1027.py`：通过
- `tests/test_runtime_binding_injection_1078.py`：通过
- `tests/test_setup_assistant_1025.py`：通过
- `tests/test_task_contract_1018.py`：通过
- `tests/test_task_schedule_panel_contract.py`：通过

### 未完成 / 环境限制

- 未执行真实 Docker 拉镜像、启动任务容器、连接私有镜像仓库的端到端测试，因为当前容器没有目标测试服 Agent、私有仓库、真实镜像和 Docker daemon 上下文。
- 未执行真实 MySQL / Redis / OSS 连通性测试，因为本轮没有对应测试环境配置和密钥。
- 后端完整 pytest 一次性运行在当前容器中存在卡住风险；拆分按文件执行通过。上线 CI 建议先采用分组执行，并后续专门隔离 preflight 外部探测测试。

## 五、后续建议

1. 设计 per-run runtime token，替换任务容器内复用 Agent Token。
2. 把 preflight 中所有外部探测测试完全 mock 化，避免 CI 卡死。
3. 增加真实 Agent + Docker + spider image 的 E2E 流水线。
4. 增加“任务绑定完整性”上线门禁：任务启用前检查 `config_bindings` / `credential_bindings` 与任务模板声明是否一致。
5. 平台稳定后，再整改爬虫项目结构标准与示例任务，避免平台契约未定时反复改业务爬虫。

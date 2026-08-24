# v1.0.79 发布候选包本地验证记录

## 验证范围

本次验证基于本地容器中的源码树执行，范围覆盖 Python 语法编译、后端契约测试、版本一致性检查、发布包卫生检查和前端构建可用性探测。

## 通过项

### Python 语法编译

```bash
python -m compileall -q backend/app agent/crawler_agent runtime/crawler_runtime backend/tests
```

结果：通过。

### 后端测试：隔离分组执行

为避免当前容器中完整 pytest 单进程执行时被历史全局状态拖慢或卡住，本轮按文件隔离执行后端测试。

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_account_status_standard.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_account_subject_binding_contract.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_alembic_graph_integrity.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_cicd_one_click_1030.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_company_resource_pool_1077.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_company_tenant_isolation_1026.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_migration_observability_recovery.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_rebuild_contract.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_release_gate_1019.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_release_package_hygiene_1079.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_release_version_scripts.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_running_center_1027.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_runtime_binding_injection_1078.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_setup_assistant_1025.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_task_contract_1018.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_task_schedule_panel_contract.py
```

结果：104 个测试全部通过。

关键分组结果：

- `tests/test_rebuild_contract.py`：65 passed。
- `tests/test_release_package_hygiene_1079.py`：3 passed。
- `tests/test_runtime_binding_injection_1078.py`：2 passed。

### 版本一致性检查

执行：

```bash
cp .env.example .env
bash deploy/scripts/check-version-consistency.sh
rm -f .env
```

结果：通过，`releaseVersion=1.0.79`，warnings=0。

## 未通过或未完成项

### 单进程完整 pytest

执行：

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests
```

当前容器中该命令在输出约 60 个测试点后超时，未作为通过项。相同测试按文件隔离执行全部通过，说明主要风险更接近测试隔离/全局状态/容器执行时长问题，而不是本次 v1.0.79 发布包卫生修复引入的业务失败。

### 前端构建

执行：

```bash
cd frontend
npm ci --prefer-offline --no-audit --fund=false
npm run build
```

当前容器中 `npm ci` 超时，随后 `npm run build` 因依赖未完整安装失败：`vue-tsc: not found`。因此本地容器未完成前端构建验证。生产或测试服上线前必须在具备 npm registry 访问能力的环境重新执行 `npm ci && npm run build`。

### 真实环境端到端

当前容器没有真实 Docker Compose 服务、MySQL、Redis、镜像仓库、Agent 节点和爬虫镜像，未验证真实端到端运行链路。

## 结论

v1.0.79 已解决 v1.0.78 审核时发现的本地开发数据库入包和发布版本残留问题，可作为测试服/准生产联调候选包。生产上线前必须补齐前端构建和真实 Agent + Docker + spider image 端到端验证。

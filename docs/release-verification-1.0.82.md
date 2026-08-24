# v1.0.82 发布候选包验证记录

## 验证项

### Python 编译

```bash
python -m compileall -q backend/app agent/crawler_agent runtime/crawler_runtime backend/tests deploy/scripts/check-alembic-graph.py
```

结果：通过。

### Shell 语法

```bash
bash -n deploy/scripts/install-agent.sh backend/app/templates/install-agent.sh deploy/scripts/commercial-release-gate.sh
```

结果：通过。

### 关键接入契约测试

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q \
  tests/test_agent_bootstrap_resume_guard_1082.py \
  tests/test_agent_onboarding_ui_1081.py \
  tests/test_release_package_hygiene_1079.py \
  tests/test_runtime_binding_injection_1078.py
```

结果：`12 passed`。

### Agent Join / Bootstrap 回归测试

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q \
  tests/test_rebuild_contract.py::test_agent_join_token_bootstrap_and_install_script \
  tests/test_rebuild_contract.py::test_agent_join_token_blocks_mismatched_agent_image_runtime_target \
  tests/test_rebuild_contract.py::test_agent_bootstrap_resume_env_reuses_long_credential_without_join_token \
  tests/test_rebuild_contract.py::test_unhealthy_agent_can_be_cleaned_and_rejoined \
  tests/test_rebuild_contract.py::test_orphan_join_invitation_can_be_cleaned_and_disappears \
  tests/test_rebuild_contract.py::test_agent_join_command_preserves_detected_external_port
```

结果：`6 passed`。

### 版本一致性

```bash
cp .env.example .env
bash deploy/scripts/check-version-consistency.sh
rm -f .env
```

结果：通过，`releaseVersion=1.0.82`，`warnings=0`。

### ZIP 校验

- 当前源码目录与 ZIP 解压目录 sha256 manifest 一致。
- ZIP 中无 `*.db` / `*.sqlite` / `*.sqlite3`。
- ZIP 中无 `node_modules` / `dist` / `__pycache__` / `.pytest_cache`。

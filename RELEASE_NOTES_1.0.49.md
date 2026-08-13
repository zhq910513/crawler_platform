# crawler_platform 1.0.49

## 商业发布门禁契约修复

- 修复 `test_agent_join_token_bootstrap_and_install_script` 仍要求安装脚本静态包含固定 Agent 镜像版本的问题。
- 安装脚本契约改为校验脚本具备 `AGENT_IMAGE` 读取、参数覆盖和旧版本硬编码清理能力。
- Agent 镜像版本断言移动到 bootstrap `.env`，确保控制端下发配置才是唯一可信镜像来源。
- 版本统一递增到 `1.0.49`。

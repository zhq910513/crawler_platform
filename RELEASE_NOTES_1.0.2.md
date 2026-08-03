# crawler_platform 1.0.2 Release Notes

## 本次范围

本版本按商业化商品级测试与优化要求继续加固 1.0.2，重点覆盖账号密码安全、日志 V2 基础链路、高频操作日志过滤、多时间点调度、Agent 资源状态展示、商业发布门禁和售后 Runbook。

## 主要变更

### 账号密码安全

- 新增当前用户修改密码规范接口：`PATCH /api/v1/users/me/password`。
- 兼容保留旧接口：`PATCH /api/v1/users/current/passwords`。
- 新增超级管理员重置用户密码接口：`POST /api/v1/users/{userId}/password-resets`。
- `sys_user` 新增 `password_updated_at`、`must_change_password`。
- 登录响应新增 `passwordChangeRequired`，前端登录后可强制改密。
- 修改/重置密码后撤销目标用户现有会话，旧 token 失效。
- 密码明文不进入操作日志。

### 日志 V2 基础链路

- `crawler_task_run` 增加日志状态、日志大小、尾部序号、失败阶段、错误类型、错误摘要、重试建议、诊断 JSON 等字段。
- 新增 `crawler_run_event` 生命周期事件表。
- 新增 `crawler_run_log_chunk` 日志分片表。
- Agent 新增运行事件、日志分片、日志完成上报接口。
- 前端执行记录页支持生命周期、日志尾部、诊断信息和日志下载。
- 修正前端日志接口路径，统一使用后端 REST 资源：`/log-tails`、`/diagnoses`、`/log-downloads`。

### 操作日志过滤

- API 审计中间件过滤 Agent 高频接口：心跳、领取任务、运行心跳、结果、事件、日志分片、日志完成上报。
- 保留用户手工管理动作审计，避免 `sys_operation_log` 被运行链路污染。

### 多时间点调度

- `cron-previews` 支持 `scheduleConfig`：`daily_times`、`weekly_times`、`monthly_times`。
- 支持每日多个时间点、每周多日期 + 多时间点、每月多日期 + 多时间点。
- 支持不同分钟的多时间点，例如 `07:15`、`09:45`、`12:00`。
- 多时间点由内置调度服务转换为单个或多个 5 段 Cron，多个表达式用分号连接。
- `crawler_task_schedule.cron_expression` 扩展到 1000 字符。
- 前端任务调度弹窗新增每周/每月多日期多时间点配置和预览。

### Agent 资源状态

- Agent 心跳上报 CPU、内存、磁盘、inode、容器槽位、Docker 状态、Docker Sock 可访问性、项目目录可写性、时区等指标。
- 服务器列表页展示健康状态、容量状态、资源使用率、槽位与最近错误。
- 后端根据心跳超时自动标记离线。

### 商业交付能力

- 新增商业发布门禁：`deploy/scripts/commercial-release-gate.sh`。
- 新增商业契约扫描：`deploy/scripts/commercial-contract-scan.py`。
- 新增商业化发布检查清单：`docs/commercial-release-checklist.md`。
- 新增售后运维 Runbook：`docs/commercial-operations-runbook.md`。
- 新增 1.0.1 -> 1.0.2 升级与回滚说明：`docs/upgrade-rollback-1.0.2.md`。

## 验证

- Python 编译：通过。
- Shell `bash -n`：通过。
- MySQL 标识符长度检查：通过。
- 商业契约扫描：通过。
- 后端契约/回归测试：`21 passed`。
- 商业发布门禁非严格模式：`PASS_WITH_RISK`，风险仅为当前离线环境缺少 git 工作树与 frontend/node_modules，未执行前端构建。
- 前端构建：当前离线环境缺少 `node_modules/vue-tsc/vite`，未完成 `npm run build`；正式发布门禁中该项为强制项。

## 2026-08-03 宿主机旧版本兼容加固

- 将 `doctor.sh` 调整为“最低部署条件阻断、可选工具警告”模型：只有 Docker、Docker Compose、Docker 权限等最低条件失败才退出；Python/npm/curl/git 等缺失或版本过旧只输出 WARNING。
- 新增 `deploy/scripts/container-compile-check.sh`，用 Python Docker 工具容器执行编译检查，避免客户宿主机 Python 3.6/2.7 对容器化代码产生误判。
- 新增 `deploy/scripts/host-compat-scan.py`，发布门禁会扫描部署脚本是否重新引入宿主机 Python/npm/jq 硬依赖。
- 重写 `commercial-release-gate.sh`：Python 编译、商业契约扫描、MySQL 标识符检查、后端测试、前端构建均改为 Docker 工具容器执行，不再依赖宿主机 Python/npm/node_modules。
- `smoke-test.sh` 默认改用 Python 3.12 工具容器执行；仅显式设置 `CP_USE_HOST_TOOLS=1` 且宿主机 Python 足够新时才走宿主机。
- 项目接入模板 `bootstrap.sh` / `preflight.sh` 调整为 Docker 优先：`python3`、`curl`、`git` 缺失不再直接阻断，manifest 解析和 JSON 格式化通过 Python 工具容器完成。
- `deploy.sh`、`deploy-single-server.sh`、`test-server-validate.sh` 增加体检入口，warnings 不阻断部署流程。

## 2026-08-03 迁移恢复修复

- 修复 `0002_observability.py` 在 MySQL 下 `alter_column` 缺少 `existing_type` 导致迁移失败的问题。
- 将 0002 改为幂等恢复迁移：字段、表、索引存在时自动跳过，可恢复“字段已部分添加但 alembic_version 仍停留在 0001”的半迁移状态。
- `diagnosis_json` 迁移流程调整为先补 `{}`，再执行 NOT NULL 约束变更。
- `0003_schedule_cron_len.py` 增加当前字段长度判断，已扩展到 1000 时自动跳过，避免重复执行风险。
- 新增迁移回归测试 `backend/tests/test_migration_observability_recovery.py`，覆盖 0002 半迁移恢复与 0003 幂等执行。
- 修正 0002/0003 Alembic revision id 长度，避免 MySQL 默认 `alembic_version.version_num VARCHAR(32)` 写入长版本号失败。

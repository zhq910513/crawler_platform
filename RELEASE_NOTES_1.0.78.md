# crawler_platform v1.0.78 发布说明

发布日期：2026-08-24

## 核心修复

本版本修复平台正式任务“配置绑定 / 账号绑定”未进入爬虫运行时的契约断点。

v1.0.77 中，任务保存了 `config_bindings` 和 `credential_bindings`，但运行实例快照与 Agent 下发 payload 主要只包含业务参数 `parameters`。当爬虫项目通过 `context.config` 和 `context.accounts` 读取平台资源和账号时，可能无法拿到正式绑定信息。

v1.0.78 统一在运行实例创建时构造运行时参数，并在 Agent 认领任务时显式下发：

- `configBindings`
- `config_bindings`
- `credentialBindings`
- `credential_bindings`
- `accounts`

## 变更内容

- `RunService` 新增统一运行参数构造逻辑，单实例任务与分片父任务均写入完整运行契约快照。
- `AgentService` 认领任务时显式返回配置绑定、凭据绑定和账号槽位；对升级前旧快照增加轻量自愈。
- `DockerRunner` 向任务容器注入运行时配置 JSON、账号状态上报端点、凭据租约端点和 Agent 身份。
- 新增 `backend/tests/test_runtime_binding_injection_1078.py`，覆盖运行快照和 Agent 下发契约。
- 平台版本同步提升到 `1.0.78`。

## 未改变的契约

- 未新增数据库字段。
- 未修改公司级资源配置模型。
- 未修改 Redis / OSS / 数据库客户端初始化方式。
- 未修改爬虫项目代码。
- 未把配置绑定解析成真实连接对象；本版本只保证平台保存的绑定引用能进入运行时。

## 风险说明

当前任务容器为了访问账号状态和租约 API，仍沿用现有 Agent 鉴权方式。后续建议新增 per-run、短 TTL、限定端点的 runtime token，以进一步收敛任务容器权限。

## 测试

已通过语法编译、运行契约回归测试和后端测试分组执行。当前容器环境中，后端完整 pytest 一次性运行存在卡住风险，已记录在 `docs/backend-runtime-contract-audit-1.0.78.md`。

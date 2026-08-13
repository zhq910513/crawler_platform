# crawler_platform 1.0.19 发布说明

## 版本主题

运行前契约强校验、真实账号租约、对象账号亲和绑定并发保护、非账号事件状态隔离，补齐 1.0.18 审查发现的上线阻断项。

## 关键变更

- 任务创建/更新时强制校验 `requiredConfigs` 与 `requiredCredentials`：必填绑定项缺失、账号绑定模式不匹配、亲和绑定缺少 `subjectType`、外部亲和绑定缺少 `externalField` 时拒绝保存。
- 新增账号租约表与 API：`/credential-leases/acquire`、`/credential-leases/release`、Agent 侧租约接口，避免账号池并发抢占。
- 账号状态事件中 `affectsCredential=false` 不再刷新账号 `lastVerifiedAt/statusFreshUntil/healthStatus/loginStatus`，只记录非账号类问题元数据。
- 对象账号亲和绑定创建使用数据库唯一约束与行锁语义保护，已绑定对象不会被后续成功事件自动覆盖。
- 补充上线级回归测试：任务契约门禁、账号租约生命周期、非账号事件隔离。

## 上线注意

- Alembic head 更新为 `0009_contract_runtime_gate`。
- 上线前仍需在 CI/部署机执行前端构建与商业发布门禁。

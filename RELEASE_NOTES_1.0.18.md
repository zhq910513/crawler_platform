# crawler_platform 1.0.18 发布说明

本版本在 1.0.17 账号状态上报规范基础上，继续落地“前端操作合约、任务契约校验、对象账号亲和绑定”。

## 新增能力

- 任务定义契约增强：平台解析 `platformCode`、`requiredConfigs`、`requiredCredentials`、`outputTables`、`contractVersion`。
- 项目任务定义新增契约状态：`contractStatus`、`contractWarnings`。
- 正式任务新增运行配置引用：`configBindings`、`credentialBindings`、`contractSnapshot`。
- 账号状态事件新增业务对象字段：`subjectType`、`subjectKey`、`subjectName`、`affectsCredential`。
- 新增对象账号绑定表 `crawler_credential_subject_binding`。
- 新增对象账号绑定 API：
  - `GET /api/v1/credential-subject-bindings`
  - `POST /api/v1/credential-subject-bindings`
  - `PATCH /api/v1/credential-subject-bindings/{bindingId}`
- 账号状态事件可自动创建/更新对象账号亲和绑定。
- 已有绑定遇到不同账号上报时只记录冲突，不自动覆盖原绑定。
- 前端账号状态页面新增对象账号绑定列表和前端操作合约提示。

## 设计约束

- 平台不高频扫描客户账号缓存库。
- 账号状态统一通过公共组件上报。
- 对象账号绑定默认只允许人工换绑。
- 任务调度只保存配置/账号引用，不保存 Cookie、Token、密码、API key 明文。

## 校验

- 后端测试：`53 passed`
- Alembic 图检查：唯一 head `0008_task_contract`

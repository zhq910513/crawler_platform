# 前端操作合约与账号绑定标准（crawler_platform 1.0.19）

## 目标

本版本将多公司、多平台、多账号、多业务任务的前端操作固定为一个简单合约：

1. 公司管理负责公司边界和用户权限。
2. 数据资源配置负责公司级 MySQL、PostgreSQL、SQL Server、Redis、MongoDB、OSS、S3、MinIO 等资源；同一家公司允许多种类型共存，也允许同类型多个实例，并通过资源名称、编码、用途和备注区分。
3. 平台管理负责被爬平台模板、账号类型和字段模板。
4. 平台账号负责公司在某个平台下的多个账号、启用状态、健康状态、登录态状态、临时 Cookie/API Token 状态。
5. 项目管理接收 CI/CD 注册的 release，并主动发现代码里的 `TASK_DEFINITION`。
6. 任务计划只负责把系统发现的平台任务绑定数据库绑定项、账号绑定项和自动计划时间。
7. 爬虫代码只通过 `context.config` 与 `context.accounts` 取配置和账号，不硬编码公司账号、Cookie、Token、数据库连接。

## 任务发现合约

爬虫项目必须在每个业务任务中提供静态 `TASK_DEFINITION`。平台 1.0.19 会解析以下字段：

- `platformCode`：被爬平台编码。
- `requiredConfigs`：任务需要的数据库/缓存/OSS 配置绑定项。
- `requiredCredentials`：任务需要的账号绑定项。
- `outputTables`：任务会写入的表。
- `allowOfflineRun` / `offlinePolicy`：离线兜底策略。

如果缺少 `platformCode` 或账号/配置绑定项结构不规范，平台不会中断历史兼容任务，但会将任务契约标记为 `WARNING` 并保存 `contractWarnings`，供项目管理和任务调度页面提示。

## 账号绑定模式

任务调度里只保存账号引用，不保存 Cookie、Token、密码、API key 明文。

支持的账号绑定模式：

- `fixed`：固定单账号，对应 `context.accounts.get(slot)`。
- `fixed_list`：固定多个账号，对应 `context.accounts.list(slot)`。
- `pool`：普通账号池，对应 `context.accounts.lease(slot)`。
- `binding_rule`：按店铺/品牌/区域等规则匹配账号，对应 `context.accounts.resolve(slot, subject)`。
- `affinity_pool`：对象首次成功后绑定账号，后续强制复用，对应 `context.accounts.affinity(...)`。
- `external_affinity_pool`：兼容外部业务对象缓存字段，例如公司列表里的 `credential_key`，对应 `context.accounts.external_affinity(...)`。

## 对象账号亲和绑定

当某个业务对象第一次由某个账号成功查询后，平台可以保存绑定关系：

```text
companyCode + platformCode + subjectType + subjectKey -> credentialKey
```

典型场景：某平台有 5 个账号查询大量公司信息。某公司第一次被 `account_b` 查询成功后，后续该公司必须继续用 `account_b` 查询。

平台新增 `crawler_credential_subject_binding` 保存该关系，并支持：

- 任务运行成功事件自动建立绑定。
- 后续成功更新最后成功时间。
- 不自动换绑，默认 `MANUAL_ONLY`。
- 如果另一个账号对同一对象上报成功，记录冲突到事件 payload，不覆盖原绑定。
- 管理员可人工换绑并留下原因与审计字段。

## 账号状态来源

平台展示的是最后已知状态，不承诺实时扫描：

- 任务运行反馈。
- 人工测试/手动上报。
- Agent 指定探测。
- 过期时间推导。

平台不会高频访问公司的 Redis/Mongo/MySQL/Cookie 缓存库判断账号是否存活。

## 泄露控制

账号状态事件、对象绑定事件、任务调度配置都禁止保存明文敏感信息。平台会对以下字段自动脱敏：

- cookie、token、authorization
- password、secret、access key、private key
- phone、mobile、email token

运行时真实凭证应通过 `runtimeSecretBundle` 或外部缓存引用在 Agent 侧临时解析，任务完成后由 Agent 清理。

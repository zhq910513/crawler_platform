# crawler_platform 1.0.17 发布说明

本版本在 1.0.16 Agent 接入、项目部署中心和离线兜底基础上，新增“账号状态上报规范”的平台侧落地。

## 核心变化

- 新增账号状态中心，不要求平台频繁访问各公司 Redis/Mongo/MySQL/Cookie 缓存库。
- 统一使用 `companyCode/companyId + platformCode + credentialKey` 定位账号。
- 新增账号当前状态字段：`enabled`、`healthStatus`、`loginStatus`、`usageStatus`、`lastStatusCode`、`statusFreshUntil`。
- 新增账号状态事件表，所有状态变化先落事件，再聚合为账号最后已知状态。
- 新增用户侧和 Agent 侧账号状态上报接口。
- 状态事件入库前统一脱敏，禁止保存 cookie、token、password、secret、手机号等敏感字段。
- 支持旧项目逐步迁移：账号凭证可以仍在公司缓存库中，爬虫只需要通过公共组件上报状态。

## API

- `POST /api/v1/account-status-events`：登录用户手动或工具上报账号状态。
- `POST /api/v1/agent-account-status-events`：Agent 代任务上报账号状态。
- `GET /api/v1/account-credentials`：查询公司账号状态列表。
- `GET /api/v1/account-credentials/{credentialId}/status-events`：查询账号状态事件。
- `PATCH /api/v1/account-credentials/{credentialId}/enabled`：启用或禁用账号。

## 状态规范

所有账号统一使用相同状态字段，不管实际凭证存在平台 Vault、公司 Redis、Mongo、MySQL、外部账号库，还是人工临时 Cookie。

标准定位键：

```text
companyCode + platformCode + credentialKey
```

平台维护“最后已知状态”和状态新鲜度，不伪装成实时探测结果。

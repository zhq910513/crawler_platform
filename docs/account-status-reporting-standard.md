# 账号状态上报规范（crawler_platform 1.0.46）

## 目标

爬虫平台不频繁访问各公司 Redis、Mongo、MySQL 或 Cookie 缓存库来判断账号是否可用。账号状态统一由任务运行反馈、人工测试、Agent 按需探测和过期时间推导更新。

## 标准定位键

所有账号状态事件必须使用以下字段定位账号：

```text
companyCode/companyId + platformCode + credentialKey
```

`credentialKey` 是业务稳定唯一编码，不要求等于真实账号、邮箱、手机号或店铺 ID。

## 统一状态字段

账号当前状态统一保存到 `crawler_account_credential`：

- `enabled`：人工启停。
- `healthStatus`：`UNKNOWN / HEALTHY / WARNING / EXPIRED / INVALID / NEED_VERIFY / DISABLED`。
- `loginStatus`：`NO_AUTH / AUTH_ACTIVE / AUTH_EXPIRED / AUTH_INVALID / MANUAL_REQUIRED`。
- `usageStatus`：`AVAILABLE / IN_USE / COOLDOWN / LOCKED / QUOTA_LIMITED`。
- `lastStatusCode`：最后一次状态码。
- `lastVerifiedAt`：最后验证时间。
- `statusFreshUntil`：状态可信截止时间。

平台页面展示的是“最后已知状态”，不是实时探测结果。

## 状态事件

所有账号状态变化先写入 `crawler_account_status_event`，再由服务聚合到账号当前状态。

核心接口：

```text
POST /api/v1/account-status-events
POST /api/v1/agent-account-status-events
GET /api/v1/account-credentials
GET /api/v1/account-credentials/{credentialId}/status-events
PATCH /api/v1/account-credentials/{credentialId}/enabled
```

## 敏感信息要求

状态事件禁止包含：Cookie、Token、密码、passwordHash、emailToken、手机号、完整请求头、完整响应体。

平台会对 `message` 和 `payload` 做基础脱敏，但业务代码仍不得主动上报敏感原文。

## 推荐状态码

成功类：`LOGIN_OK`、`COOKIE_OK`、`TOKEN_OK`、`ACCOUNT_OK`。

登录态异常：`COOKIE_EXPIRED`、`COOKIE_INVALID`、`TOKEN_EXPIRED`、`TOKEN_INVALID`、`LOGIN_FAILED`。

人工接管：`CAPTCHA_REQUIRED`、`EMAIL_VERIFY_REQUIRED`、`PHONE_VERIFY_REQUIRED`、`TWO_FACTOR_REQUIRED`。

平台限制：`RATE_LIMITED`、`QUOTA_LIMITED`、`ACCOUNT_DISABLED_BY_PLATFORM`、`ACCOUNT_LOCKED_BY_PLATFORM`。

环境异常：`NETWORK_ERROR`、`PLATFORM_5XX`、`PLATFORM_MAINTENANCE`。

网络类异常不会直接把账号判定为失效，避免误伤。

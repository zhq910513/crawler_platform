# v1.0.86 运行时公司资源配置解析审计

## 背景

爬虫业务任务应该只声明需要哪些配置，并在运行时通过标准 `context.config` 读取平台授权的公司资源配置。业务代码不得硬编码数据库地址、账号密码，也不得通过任务参数临时传生产连接串。

v1.0.85 之前，平台已经会把正式任务保存的 `configBindings` 注入 Run Snapshot 和 Agent claim payload，但这些值仍主要是 `config:<resource_code>` 之类的绑定引用。业务容器没有得到已解析的 Mongo/MySQL/Redis/OSS 连接配置。

## 本轮目标

```text
Production Task.config_bindings
    ↓
CrawlerTaskRun.parameters_snapshot 仅保存绑定引用
    ↓
Agent claim run 时临时解析 CompanyResourceConfig
    ↓
claim response 返回 configs/runtimeConfigs
    ↓
DockerRunner 注入 CRAWLER_CONFIG_JSON
    ↓
crawler_runtime / crawler_foundation context.config.<type>(slot)
```

## 已实现

### 1. RuntimeResourceResolver

新增：

```text
backend/app/services/runtime_resource_service.py
```

职责：

- 解析绑定格式：
  - `config:<resource_code>`
  - `resource:<resource_code>`
  - `company_resource:<resource_code>`
  - `resourceId` / `configId`
  - `resourceCode` / `configRef` / `resourceRef`
- 按 `company_id` 与 `project_id` 查找资源。
- 项目级资源优先于公司级资源。
- 校验资源启用状态、测试状态、资源类型。
- 解密 `config_encrypted` 并只返回给 claim payload。

### 2. Agent claim run 下发 resolved configs

`AgentService.claim_run()` 现在返回：

```json
{
  "configBindings": {"mongo_jdd": {"resourceCode": "jdd_result_mongo"}},
  "configs": {
    "mongo_jdd": {
      "uri": "mongodb://...",
      "database": "jdd",
      "resourceCode": "jdd_result_mongo",
      "resourceEngine": "MONGODB",
      "connectionMode": "URI"
    }
  },
  "runtimeConfigs": {...}
}
```

### 3. Run Snapshot 不落明文

`CrawlerTaskRun.parameters_snapshot` 保持：

```json
{
  "configBindings": {"mongo_jdd": {"resourceCode": "jdd_result_mongo"}},
  "config_bindings": {"mongo_jdd": {"resourceCode": "jdd_result_mongo"}}
}
```

不会写入：

```text
Mongo URI
MySQL password
Redis password
OSS access secret
```

### 4. DockerRunner 注入标准配置 JSON

`CRAWLER_CONFIG_JSON` 新增 resolved configs：

```json
{
  "configs": {...},
  "config": {...},
  "configBindings": {...},
  "config_bindings": {...}
}
```

这样现有 `RuntimeConfigResolver` 会优先从 `configs` 读取真实配置，仍保留 `configBindings` 作为审计引用。

## 没有修改的契约

- 没有新增数据库字段。
- 没有修改 `CompanyResourceConfig` 加密格式。
- 没有修改 Agent 鉴权协议。
- 没有要求业务容器反查平台数据库。
- 没有在平台里创建 MongoClient/MySQL/Redis/OSS 客户端。

## 下一步

爬虫项目应在 v1.0.15 按以下方向整改：

```text
spiders/jdd/base.py       读取 context.config.mongo("mongo_jdd")
spiders/jdd/items.py      只保留业务参数，不再接受 mongoUri/mongoConfig
open_api/jdd/items_client.py  只负责请求，不负责入库
TASK_DEFINITION.requiredConfigs.mongo_jdd.required = true
```

# crawler_platform v1.0.77 发布说明

## 主题

重构公司级多数据资源配置模型。

本版将旧的“数据库配置”升级为“数据资源配置”，不再使用 `MYSQL_MAIN / REDIS_CACHE / MONGO_RAW / OSS_MEDIA` 这种把数据库类型和业务用途混在一起的旧模型。新模型显式拆分：

- `resourceCategory`：资源大类，例如关系型数据库、文档数据库、缓存数据库、对象存储。
- `resourceEngine`：具体类型，例如 MySQL、PostgreSQL、SQL Server、MongoDB、Redis、OSS、S3、MinIO。
- `resourceRole`：业务用途，例如主业务数据库、采集结果库、客户源数据库、原始数据存储、账号缓存、媒体文件存储。
- `connectionMode`：连接方式，例如主机端口、URI、云服务。

## 核心变化

- 每条数据资源必须归属公司。
- 项目归属可选，支持公司级共享资源和后续项目专属资源扩展。
- 同一家公司允许多种数据库/存储类型共存。
- 同一家公司允许多个同类型资源，例如多个 MySQL、多个 Redis、多个 MongoDB。
- 新增 `resourceName`、`resourceCode`、`remark`，备注用于说明这个资源具体做什么。
- 新增 `company_resource_config` 专表，非敏感元数据可查询、可筛选，敏感连接配置继续加密保存。
- 新增基础配置校验状态：`CONFIG_VALID / CONFIG_INVALID / MANUAL_CONFIRMED`。
- “配置完整”不再等同于“连接通过”。v1.0.77 不执行真实数据库连通测试。
- 旧版 `sys_secret` 中的公司资源配置会迁移到新表，并保留 `legacyResourceType` 兼容字段。

## 不包含

本版不做真实 MySQL、PostgreSQL、SQL Server、MongoDB、Redis 或对象存储连通测试；连接工厂和真实连通测试计划放到后续版本。

## 提交信息

```bash
-m "重构公司级多数据资源配置模型v1.0.77"
```

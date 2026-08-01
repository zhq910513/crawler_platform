# 爬虫管理平台

本版本按冻结方案从零重建：平台数据库是唯一调度事实来源，`sch.py` 只作为项目任务清单声明来源；项目通过执行服务器池调度，Agent 仅负责资源上报、精确镜像 digest 校验、容器执行、租约心跳和结果回传。

## 核心变化

- 所有 API 返回 `{ "code": 200, "message": "success", "data": ... }`。
- 前后端 JSON 字段统一 camelCase，数据库字段保持 snake_case。
- 后端采用 Controller/API → Service → Repository 三层结构。
- 普通用户强制限制在账户归属公司内，并继续受项目成员权限控制。
- 所有账号只允许单会话，十分钟内有有效操作视为在线，新登录需确认强制登录。
- 项目接入改为公司级发现凭证 → 待接入项目 → 正式项目。
- `sch.py` 只解析任务目录，正式任务必须由前端从任务定义中创建。
- 项目使用多服务器执行池，支持主备和负载均衡；同一任务多机运行预留为任务层分片能力。
- 调度先创建运行实例，再动态路由服务器；无资源时进入等待资源，不丢 Cron 触发。
- 告警通知先预留飞书、企业微信、钉钉、邮箱基础配置，只有 P0 才外发。

## 上线检查命令

所有命令均为单行。宿主机最小依赖为 Docker + Docker Compose；Python/npm 等复杂能力优先通过工具容器或平台容器执行。

环境体检：`./deploy/scripts/doctor.sh`

国内镜像源配置：`./deploy/scripts/prepare-cn-mirrors.sh --yes`

零数据测试服验收：`./deploy/scripts/test-server-validate.sh --yes --prepare-cn-mirrors`

只跑 smoke-test：`./deploy/scripts/test-server-validate.sh --yes --skip-reset`

生产部署：`./deploy/scripts/deploy.sh`

查看容器：`docker compose ps`

查看 API 日志：`docker compose logs --tail=300 api`

查看调度器日志：`docker compose logs --tail=300 scheduler`

查看维护进程日志：`docker compose logs --tail=300 maintenance`

查看前端日志：`docker compose logs --tail=200 web`

后台健康检查：`curl -fsS http://127.0.0.1:8080/health`

## API 约定

- 登录：`POST /api/v1/sessions`
- 当前会话：`GET /api/v1/sessions/{sessionId}`
- 公司：`GET/POST /api/v1/companies`
- 项目接入凭证：`POST /api/v1/companies/{companyId}/discovery-tokens`
- 待接入项目：`GET/POST /api/v1/discovered-projects`
- 正式项目：`GET/POST /api/v1/projects`
- 项目执行服务器池：`GET/PUT /api/v1/projects/{projectId}/servers`
- 任务定义：`GET /api/v1/projects/{projectId}/task-definitions`
- 正式任务：`GET/POST /api/v1/tasks`
- 执行记录：`GET/POST /api/v1/runs`
- 告警通知配置：`GET/POST /api/v1/notification-channels`

## 项目 Manifest 示例

```json
{
  "manifestVersion": "1",
  "projectKey": "baidu-shop-detail",
  "projectName": "百度爱采购店铺详情抓取",
  "projectCode": "baidu_shop_detail",
  "repositoryUrl": "git@example.com:spiders/baidu_shop_detail.git",
  "imageRepository": "registry.example.com/spiders/baidu_shop_detail",
  "imageDigest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "releaseVersion": "1.0.0",
  "releaseChannel": "stable",
  "taskDefinitions": [
    {
      "definitionKey": "shop_detail",
      "taskName": "店铺详情抓取",
      "entryModule": "spiders.baidu_shop_detail.main",
      "entryFunction": "run",
      "suggestedCron": "0 */1 * * *",
      "executionMode": "SINGLE",
      "idempotencyPolicy": "IDEMPOTENT"
    }
  ]
}
```

## 运行模式说明

默认运行模式为“项目环境镜像 + 独立任务容器”：一个项目构建一个不可变镜像环境，任务容器共享镜像层和项目缓存卷，但每个运行实例仍拥有独立容器、工作目录、日志目录和资源限制。详见 `docs/共享环境隔离运行模式.md`。

## 零数据测试服一键验收

测试服按 Fresh Install 标准验收：空 MySQL、空 Redis、空项目数据目录开始。

一键重置并执行核心链路验收：

```bash
./deploy/scripts/test-server-validate.sh --yes
```

只执行 smoke-test，不清空已有测试服数据：

```bash
./deploy/scripts/test-server-validate.sh --yes --skip-reset
```

详细步骤见：`docs/部署工程化核心要点.md`。

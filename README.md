# 爬虫管理平台

本版本按冻结方案从零重建：平台数据库是唯一调度事实来源，`sch.py` 只作为项目任务清单声明来源；项目通过执行节点范围分配运行，Agent 仅负责资源上报、精确镜像 digest 校验、容器执行、租约心跳和结果回传。

## 核心变化

- 所有 API 返回 `{ "code": 200, "message": "success", "data": ... }`。
- 前后端 JSON 字段统一 camelCase，数据库字段保持 snake_case。
- 后端采用 Controller/API → Service → Repository 三层结构。
- 普通用户强制限制在账户归属公司内，并继续受项目成员权限控制。
- 所有账号只允许单会话，十分钟内有有效操作视为在线，新登录需确认强制登录。
- 项目接入改为公司级发现凭证 → 待接入项目 → 正式项目。
- `sch.py` 只解析任务目录，正式任务必须由前端从任务定义中创建。
- 项目支持多执行节点运行范围，支持主备和负载均衡；同一任务多机运行预留为任务层分片能力。
- 任务计划先创建运行实例，再动态分配执行节点；无资源时进入等待资源，不丢 Cron 触发。
- 告警通知先预留飞书、企业微信、钉钉、邮箱基础配置，只有 P0 才外发。

## 上线检查命令

所有命令均为单行。宿主机最小依赖为 Docker + Docker Compose；Python/npm 等复杂能力优先通过工具容器或平台容器执行。

环境体检：`bash deploy/scripts/doctor.sh`

容器化 Python 编译检查：`bash deploy/scripts/container-compile-check.sh`

商业发布门禁：`bash deploy/scripts/commercial-release-gate.sh`

国内镜像源配置：`bash deploy/scripts/prepare-cn-mirrors.sh --yes`

零数据测试服验收：`bash deploy/scripts/test-server-validate.sh --yes --prepare-cn-mirrors`

只跑 smoke-test：`bash deploy/scripts/test-server-validate.sh --yes --skip-reset`

生产部署：`bash deploy/scripts/deploy.sh`

查看容器：`docker compose ps`

查看 API 日志：`docker compose logs --tail=300 api`

查看调度器日志：`docker compose logs --tail=300 scheduler`

查看维护进程日志：`docker compose logs --tail=300 maintenance`

查看前端日志：`docker compose logs --tail=200 web`

后台健康检查：`curl -fsS http://127.0.0.1/health`


## 宿主机兼容策略

宿主机最低部署条件只包括：bash、Docker daemon 可用、Docker Compose 可用、当前用户具备 Docker 权限。Python、pip、npm、node、jq、curl、git、ss、netstat、timedatectl 等均属于可选工具；缺失或版本过旧时，预检只给出 WARNING，不打断部署流程。

发布门禁、Python 编译、后端测试、前端构建、smoke-test 默认使用 Docker 工具容器执行。不要在客户服务器上直接执行 `python3 -m compileall backend agent` 作为上线判断，因为客户宿主机可能是 Python 3.6 或更旧版本，会对容器内可正常运行的代码产生误判。

需要强制使用宿主机工具时可显式设置 `CP_USE_HOST_TOOLS=1`，但仅建议研发机使用，测试服和客户服务器默认不启用。

## API 约定

- 登录：`POST /api/v1/sessions`
- 当前会话：`GET /api/v1/sessions/{sessionId}`
- 公司：`GET/POST /api/v1/companies`
- 项目接入凭证：`POST /api/v1/companies/{companyId}/discovery-tokens`
- 待接入项目：`GET/POST /api/v1/discovered-projects`
- 正式项目：`GET/POST /api/v1/projects`
- 项目执行节点范围：`GET/PUT /api/v1/projects/{projectId}/servers`
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
  "releaseVersion": "1.0.1",
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
bash deploy/scripts/test-server-validate.sh --yes
```

只执行 smoke-test，不清空已有测试服数据：

```bash
bash deploy/scripts/test-server-validate.sh --yes --skip-reset
```

详细步骤见：`docs/部署工程化核心要点.md`。

## 版本一致性与自动化发布

测试服或客户服务器上线升级时，推荐统一执行：

`bash deploy/scripts/release-upgrade.sh`

发布版本解析优先级：当前 Git tag（如 `v1.0.75`） > 最新 commit message 中的平台版本号（如 `主动修复Agent生命周期续跑与收敛缺口v1.0.75`） > 根目录 `VERSION` 文件。脚本会自动同步 `.env` 的 `APP_VERSION`、`PLATFORM_IMAGE_TAG`、`APP_GIT_COMMIT` 和 `APP_BUILD_TIME`，并在启动后校验 `/health` 返回版本，避免出现 Git 已更新但容器仍运行旧镜像标签的问题。

从 v1.0.72 起，平台版本、Agent 版本和通信协议版本正式解耦；v1.0.75 进一步修复前端镜像构建 npm 源 fallback、package-lock resolved 源治理和发布门禁失败归因。平台普通 patch 发布不再默认构建、推送或替换 Agent；当前 Agent 独立版本为 `1.1.2`，协议版本为 `1.0`。只有 Agent 代码、协议能力或最低兼容要求发生变化时，才进入独立 Agent 镜像准备和节点升级流程。首次服务器接入使用 Join Token；后续 Agent 修复、升级和恢复应复用长期 Agent Credential，不要求重新 Join。

只需要单独同步版本时，可执行：

`bash deploy/scripts/sync-runtime-version.sh`

只需要检查版本一致性时，可执行：

`bash deploy/scripts/check-version-consistency.sh`

## 测试服自动部署

项目已内置 GitHub Actions 自动部署测试服的标准入口：`.github/workflows/deploy-test-server.yml`。推送 `main` 后，流水线会先执行商业发布门禁，再通过 SSH 调用测试服本地脚本 `deploy/scripts/remote-auto-deploy.sh` 和 `deploy/scripts/release-upgrade.sh` 完成发布。

详细配置见：`docs/auto-deploy-test-server.md`。

版本统一规则：Git tag > 最新 commit message > `VERSION`。发布脚本会生成 `.release/version.json`，并同步 `.env`、后端 `/health`、前端 `/version.json`、Agent 运行版本。


## 1.0.71 执行节点接入与退役链路

1.0.71 修复执行节点 Registry 预检、Docker HTTP Registry 授权、真实镜像拉取错误、节点删除后的远端 Agent 残留以及接入记录清理问题。Registry 网络在 Join Token 消耗前验证；高风险 Docker 重启改为显式授权；在线节点清理通过 Agent 心跳指令完成退役后再删除平台记录。执行节点页面同时收敛信息密度，并统一修复 UTC 时间显示。

## 1.0.70 运行总览极简信息层级

1.0.70 将运行总览首页收敛为核心指标、平台状态和当前异常三层信息；正常状态只显示结论与少量计数，检测项、待自动验证、安全与接入建议、检测历史全部下沉到“查看详情”抽屉，避免运行首页被检测过程和历史记录占满。

## 1.0.69 运行总览事实检测纠偏

1.0.69 将运行总览从“预设管理员待办清单”纠正为“真实运行事实观察面”：主动探测失败但没有足够外部证据时使用“待场景验证”，不再自动变成运行告警；已有在线执行节点心跳、Docker 状态和实际运行镜像 digest 会作为更强运行证据。安全组、Registry 认证/TLS 等平台无法直接读取的云侧治理项独立为安全建议，不参与运行健康、异常数量或节点接入就绪判定。

## 1.0.68 Agent 镜像下发与运行版本说明

CI/CD 注册新 release 后，平台通过 Agent 心跳返回 `pendingImagePulls` 通知执行节点。Agent 仅在空闲时主动预热镜像；已有运行实例继续使用 run 快照中的旧 digest，不会被新镜像打断。详细规范见 `docs/agent-image-update-flow.md`。

## 1.0.68 账号状态上报规范

1.0.68 继续保留账号状态中心。平台不高频访问客户 Redis/Mongo/MySQL/Cookie 缓存库，账号状态统一通过 `companyCode/companyId + platformCode + credentialKey` 的状态事件上报，并聚合成账号最后已知状态。详见 `docs/account-status-reporting-standard.md`。

## Agent 镜像分发自动化（1.0.68）

平台部署或升级后，推荐执行：

```bash
bash deploy/scripts/prepare-agent-image.sh
```

脚本会自动构建 Agent 镜像、推送到内置 registry、写入 `.env` 的 `CRAWLER_AGENT_IMAGE` 并重启后端服务。云安全组/防火墙放行 5000/TCP 仍需操作员在云控制台处理。执行节点安装命令如需自动配置 HTTP 私有仓库，可追加 `--auto-configure-docker-registry`。

## 1.0.68 导航栏版本展示与 CI/CD 执行组件镜像自动化

1.0.68 保持旧版深色侧边栏风格，不改变导航宽度、菜单字体、圆角和选中态；通过固定侧边栏高度、菜单内部滚动和版本卡固定保留，解决导航项增多后左下角版本不可见的问题。

GitHub Actions 部署入口会自动传入平台服务器公网主机 `CP_DEPLOY_PUBLIC_HOST`，并在 CI/CD 场景启用 `STRICT_AGENT_IMAGE_PREPARE=1`。执行组件镜像准备脚本会据此自动写入 `CRAWLER_AGENT_IMAGE=<公网主机>:5000/crawler_platform_agent:<版本>`。如果准备失败，CI/CD 会失败并输出原因，避免部署成功后运行总览仍残留执行组件镜像地址必须处理项。

# crawler_platform

`crawler_platform` 是一个面向多公司、多项目的可视化分布式爬虫管理平台。平台本身不直接运行爬虫代码，而是作为控制面管理项目、权限、调度、版本、Agent、运行状态、日志、错误和告警。

当前架构与 `crawler_platform_spiders` V2 协议对齐：

```text
crawler_platform 管理平台
    ↓ HTTPS，Agent 主动连接
crawler_agent 爬虫服务器执行代理
    ↓ Docker
crawler_platform_spiders 单次任务容器
    ↓
具体 spiders/<platform>/...::run(context) 完成登录、翻页、解析、入库
```

核心原则：

- 平台服务器和爬虫服务器可以部署在不同机器、不同网络区域。
- 一个 TaskRun 对应一个临时 Docker 容器，任务结束后容器退出。
- 爬虫容器不持有平台认证信息，不直接回调平台。
- Agent 负责采集容器 stdout/stderr、ERROR 事件、结果文件，并实时同步平台。
- 平台通过 SSE 将 ERROR、状态和日志增量推送到前端。
- 任务只能选择 `crawler_platform_spiders` 发布清单中的 SpiderEntry，不允许执行任意 Python 模块、函数或 Shell 命令。
- 数据库资源按公司和项目隔离，只向任务下发本次运行所需的最小资源清单和密钥。

## 目录结构

```text
crawler_platform/
├── backend/                  FastAPI 控制面 API、调度器、维护服务、Alembic 迁移
├── frontend/                 Vue 3 + Element Plus 管理界面
├── agent/                    爬虫服务器 Agent，主动连接平台并管理 Docker 容器
├── cicd/                     SpiderRelease 导入示例
├── deploy/scripts/           部署、备份、恢复脚本
├── docs/                     V2 架构、运维和协议说明
├── data/                     MySQL、Redis、运行日志等持久化目录
└── docker-compose.yml
```

## 主要功能

### 控制面

- 登录认证和 JWT。
- 多公司、多项目管理。
- 公司成员和项目成员权限：`OWNER`、`OPERATOR`、`VIEWER`。
- 项目资源绑定：MySQL、MongoDB、Redis、逻辑数据库、表、Collection、密钥。
- 不可变 SpiderRelease 管理：版本、Git Commit、镜像 Digest、发布清单。
- SpiderEntry 管理：任务入口、API/Browser 镜像类型、参数 Schema、所需资源。
- 任务配置、手动运行、取消、重试、Cron 调度。
- Agent 节点注册、心跳、槽位、能力和状态监控。
- TaskRun 状态机、租约、超时、LOST、OOM、终态保护。
- 实时日志、实时 ERROR、最近错误、最终错误。
- 操作审计和基础系统配置。

### Agent

- 使用 Bootstrap Token 注册，获取 Agent Token。
- 主动向平台心跳和认领任务，平台无需连接爬虫服务器。
- 一个 TaskRun 创建一个独立容器。
- 固定容器命令：`crawler_platform_spiders run --mode server ...`。
- 本地 Spool 持久化：task、resources、secrets、stdout、stderr、events、result、finish。
- 平台断网时继续运行爬虫，网络恢复后补传日志、ERROR 和结果。
- Agent 重启后恢复未完成任务，避免重复日志和重复执行。
- 支持容器超时、取消、非零退出码、OOM、容器缺失识别。

## 管理平台部署

### 1. 准备环境

管理平台服务器需要：

- Docker Engine
- Docker Compose Plugin
- 可访问镜像仓库和 Python/npm 软件源

### 2. 初始化配置

```bash
cd crawler_platform && ./deploy/scripts/prepare.sh && cp .env.example .env && vim .env
```

生产环境必须修改 `.env` 中所有 `ReplaceWith...` 值，尤其是：

```text
MYSQL_ROOT_PASSWORD
MYSQL_PASSWORD
DATABASE_URL
REDIS_PASSWORD
REDIS_URL
JWT_SECRET
SECRET_ENCRYPTION_KEY
ADMIN_PASSWORD
CICD_TOKEN
AGENT_BOOTSTRAP_TOKEN
```

密码出现在 `DATABASE_URL` 或 `REDIS_URL` 中时，包含 `@`、`:`、`/` 等特殊字符需要 URL 编码。

### 3. 启动

```bash
docker compose build --no-cache --progress=plain && docker compose up -d && docker compose ps
```

默认访问：

```text
http://管理平台IP:8080
```

API 文档默认关闭。排障时可设置：

```text
ENABLE_API_DOCS=true
```

### 4. 数据库升级

Compose 中的 `migrate` 服务会在 API、Scheduler、Maintenance 启动前执行 Alembic 迁移。生产升级前务必先备份 MySQL：

```bash
./deploy/scripts/backup.sh
```

## 爬虫服务器 Agent 安装

将 `agent/` 目录上传到爬虫服务器后执行：

```bash
cd agent && sudo ./install-linux.sh && sudo vim /opt/crawler-agent/.env && sudo systemctl restart crawler-agent && sudo journalctl -u crawler-agent -f
```

核心配置：

```text
PLATFORM_URL=https://管理平台域名
AGENT_BOOTSTRAP_TOKEN=与平台 .env 中一致
AGENT_CODE=crawler-prod-01
SERVER_CODE=crawler-prod-01
SERVER_NAME=爬虫生产服务器01
AGENT_MAX_SLOTS=4
AGENT_CAPABILITIES=["api","browser"]
AGENT_LABELS={"region":"cn-east","network":"china"}
```

生产建议平台与 Agent 使用 HTTPS。内网临时 HTTP 测试需显式设置：

```text
AGENT_ALLOW_INSECURE_HTTP=true
```

## SpiderRelease 导入

`crawler_platform_spiders` 镜像构建完成后，CI/CD 应读取镜像中的 `RELEASE_MANIFEST.json`，调用：

```text
POST /api/cicd/spider-releases
```

示例见：

```text
cicd/github-actions-example.yml
cicd/gitlab-ci-example.yml
```

平台登记发布后，项目可将 `stable`、`canary` 等通道绑定到指定 SpiderRelease。任务只能选择该发布中正式存在的 SpiderEntry。

## 任务运行链路

```text
平台调度或手动创建 TaskRun
→ Agent 主动认领
→ 平台返回 task.json/resources.json/secrets.json 和镜像 Digest
→ Agent 创建本地运行目录并启动临时容器
→ crawler_platform_spiders 调用具体爬虫 run(context)
→ 爬虫内部完成登录、翻页、解析、入库
→ ERROR/CRITICAL 输出结构化事件
→ Agent 实时上传事件和日志
→ 平台更新 last_error 并 SSE 推送前端
→ 容器写 result.json 并退出
→ Agent 上传最终结果
→ 平台进入终态
```

## 状态说明

TaskRun 标准状态：

```text
CREATED
QUEUED
ASSIGNED
STARTING
RUNNING
CANCEL_REQUESTED
SUCCEEDED
PARTIAL_SUCCESS
SKIPPED
FAILED
CANCELLED
TIMED_OUT
LOST
```

`last_error` 表示运行期间最近一次 ERROR，任务后续可能恢复成功。`terminal_error` 表示最终导致失败、超时或丢失的错误。

## 本地开发检查

Backend：

```bash
PYTHONPATH=backend python -m unittest discover -s backend/tests -v
```

Agent：

```bash
PYTHONPATH=agent python -m unittest discover -s agent/tests -v
```

前端：

```bash
cd frontend && npm install && npm run build
```

## 注意事项

- 不要在平台任务中填写任意 Python 模块、函数或 Shell 命令。
- 不要让平台服务器访问爬虫服务器 Docker Socket。
- 不要将公司数据库密码、Cookie、Token 明文写入任务参数。
- 不要把所有公司的资源配置下发给 Agent 或容器。
- Agent 本地运行目录应定期保留和清理，默认完成任务保留 72 小时。

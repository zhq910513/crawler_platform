# crawler_platform

项目名称固定为 `crawler_platform`。目录名、压缩包名、Docker Compose 项目名和平台镜像前缀均不附加版本后缀；发布版本通过 Git Tag、Release 或镜像 Tag 管理。

这是按当前确认方案实现的可运行代码：

- 管理平台使用 Docker Compose 部署。
- 爬虫项目由 CI/CD 构建成 Docker 镜像。
- 一次任务执行对应一个临时爬虫容器。
- 管理平台只保存任务配置、运行记录、日志索引和监控数据，不保存爬虫业务数据。
- 爬虫容器直接连接独立业务数据库。
- 爬虫服务器运行宿主机 Agent，由 Agent 管理 Docker 容器。
- 权限只有 `SUPER_ADMIN` 和 `NORMAL_USER` 两种。

## 1. 目录结构

```text
crawler_platform/
├── backend/                  FastAPI API、调度器、清理 Worker
├── frontend/                 Vue 3 + Element Plus 管理界面
├── agent/                    爬虫服务器宿主机 Agent
├── runtime/                  Python 方法统一执行器，需安装进爬虫镜像
├── cicd/                     GitHub Actions / GitLab CI 示例
├── deploy/scripts/           初始化、部署和备份脚本
├── data/                     MySQL、Redis、任务日志和备份持久化目录
├── docker-compose.yml
└── .env.example
```

## 2. 已实现功能

### 平台控制端

- 用户登录和 JWT 认证
- 超级管理员、普通用户固定权限
  - 超级管理员：全部菜单和任务增删改权限。
  - 普通用户：仅任务列表、任务详情、执行记录/日志入口、修改调度时间和立即执行一次。
- 用户管理
- 爬虫项目管理
- CI/CD 镜像版本登记
- 固定镜像、发布通道、最新成功构建三种版本策略
- 任务新增、编辑、删除和查询
- Cron 调度和仅手动任务
- 普通用户修改调度时间
- 普通用户立即执行一次
- 任务重叠策略：跳过、排队、允许并发、停止旧任务
- 超时控制
- 失败重试和固定/指数退避
- 任务运行实例及状态生命周期
- 运行日志查看
- 容器事件记录
- 服务器 Agent 心跳
- CPU、内存、磁盘、负载和 Docker 镜像空间监控
- 用户操作日志
- 普通配置和加密密钥管理
- 历史性能数据和日志自动清理

### 爬虫 Agent

- Bootstrap Token 注册
- Agent 独立 Token 认证
- 主动领取任务，不需要 SSH
- 拉取指定镜像摘要
- 创建独立任务容器
- 注入普通环境变量和加密密钥
- Volume、网络、CPU、内存、共享内存和进程数限制
- 实时采集 stdout/stderr
- 任务心跳和租约续期
- 人工停止和超时停止
- OOM、非零退出码等异常识别
- 成功或失败后的容器清理

## 3. 管理平台部署

### 3.1 准备环境

服务器需要安装：

- Docker Engine
- Docker Compose Plugin
- Git

### 3.2 初始化配置

```bash
cd crawler_platform
./deploy/scripts/prepare.sh
vim .env
```

必须修改 `.env` 中全部 `ReplaceWith...` 配置，特别是：

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

注意：`DATABASE_URL` 和 `REDIS_URL` 中的密码需要与前面的 MySQL、Redis 密码一致。密码中包含 `@`、`:`、`/` 等 URL 特殊字符时，应进行 URL 编码。

### 3.3 构建并启动

```bash
./deploy/scripts/deploy.sh
```

或手动执行：

```bash
docker compose build --no-cache --progress=plain
docker compose up -d
docker compose ps
docker compose logs -f api scheduler worker web
```

默认访问地址：

```text
http://管理平台IP:8080
```

账号来自 `.env`：

```text
ADMIN_USERNAME
ADMIN_PASSWORD
```

API 文档：

```text
http://管理平台IP:8080/docs
```

生产环境建议通过外层 Nginx、VPN 或访问控制限制 `/docs` 和 `/openapi.json`。

## 4. 爬虫镜像接入统一运行器

`PYTHON_METHOD` 模式依赖 `crawler-runtime`。在爬虫项目 Dockerfile 中加入：

```dockerfile
COPY runtime /tmp/crawler-runtime
RUN pip install /tmp/crawler-runtime \
    && rm -rf /tmp/crawler-runtime
```

如果 CI/CD 构建上下文无法直接访问平台项目中的 `runtime`，可以把 `runtime/crawler_runtime` 复制进爬虫代码仓库，或发布成公司的私有 Python 包。

平台配置的业务入口示例：

```text
openApi.ufl.ufl_inventory:wms_uf_eplusss_inventory
```

最终容器内会执行：

```bash
python -m crawler_runtime \
  --entrypoint openApi.ufl.ufl_inventory:wms_uf_eplusss_inventory \
  --args-json '[]' \
  --kwargs-json '{"site":"HK"}'
```

任务函数抛出异常时，运行器打印完整 traceback 并返回退出码 `1`；正常完成返回 `0`。

## 5. 安装爬虫服务器 Agent

在爬虫服务器上传 `agent` 目录：

```bash
cd agent
sudo ./install-linux.sh
sudo vim /opt/crawler-agent/.env
sudo systemctl restart crawler-agent
sudo systemctl status crawler-agent
sudo journalctl -u crawler-agent -f
```

关键配置：

```text
PLATFORM_URL=http://管理平台IP:8080
AGENT_BOOTSTRAP_TOKEN=与平台 .env 完全一致
SERVER_CODE=crawler-prod-01
SERVER_NAME=爬虫生产服务器01
SERVER_IP=服务器实际IP
MAX_CONTAINER_SLOTS=4
```

Agent 当前通过 Docker Socket 管理宿主机容器，因此 systemd 服务默认使用 root。生产服务器应限制 Agent 安装目录、配置文件和平台网络访问权限。

## 6. 创建项目和登记镜像

先在“项目与镜像”中创建项目：

```text
项目编码：ulike_overseas_scraper
Registry：registry.example.com
Repository：crawlers/ulike-overseas-scraper
```

CI/CD 构建成功后调用：

```bash
curl --request POST 'http://管理平台IP:8080/api/cicd/image-versions' \
  --header 'X-CICD-Token: 平台CICD_TOKEN' \
  --header 'Content-Type: application/json' \
  --data '{
    "project_code": "ulike_overseas_scraper",
    "image_tag": "20260724-8f19c2a",
    "image_digest": "sha256:完整镜像摘要",
    "git_branch": "main",
    "git_commit": "8f19c2a",
    "pipeline_id": "521",
    "build_status": "SUCCESS",
    "build_url": "流水线地址"
  }'
```

完整示例位于：

```text
cicd/github-actions-example.yml
cicd/gitlab-ci-example.yml
```

## 7. 新增任务建议配置

生产任务建议：

```text
镜像策略：PINNED
拉取策略：IF_NOT_PRESENT
最大并发：1
重叠策略：SKIP
失败重试：按业务决定
自动删除容器：开启
失败后保留容器：关闭
```

浏览器自动化任务建议适当增大：

```text
内存限制
共享内存 shm_size_mb
执行超时时间
```

## 8. 密钥管理

先在“系统设置 → 密钥管理”创建：

```text
密钥编码：business_mysql_pwd
```

任务中的密钥引用填写：

```json
{
  "MYSQL_PWD": "business_mysql_pwd"
}
```

平台数据库只保存加密后的密钥。Agent 领取任务时，平台通过 HTTPS 将解密后的值发送给对应 Agent，并注入本次任务容器。生产环境必须启用 HTTPS，避免密钥明文经过不安全网络。

普通环境变量不要放密码：

```json
{
  "APP_ENV": "production",
  "MYSQL_HOST": "business-mysql.internal"
}
```

## 9. 日志和监控

任务完整日志保存在管理服务器：

```text
data/task-logs/YYYY-MM-DD/task_<任务ID>/run_<运行编号>.log
```

MySQL 只保存日志路径、大小、最后日志时间和运行摘要，不保存大段日志正文。

服务器性能默认：

- Agent 每 15 秒上报最新状态
- 平台每分钟保存一条历史性能记录
- 默认保留 14 天
- 任务日志默认保留 30 天

## 10. 数据备份

```bash
./deploy/scripts/backup.sh
```

备份保存到：

```text
data/backups/
```

脚本默认清理 30 天前的 SQL 压缩备份。

## 11. 当前功能边界

当前代码已完成核心调度闭环，以下功能可在后续迭代中增加：

- 邮件、飞书和企业微信告警
- 镜像自动清理策略
- HTTPS 自动证书配置
- Agent 在线升级
- 多管理节点高可用
- Kubernetes 执行器
- 更细的容器实时资源监控
- 任务工作流和上下游依赖
- 数据质量检测

当前代码已经按远程多爬虫服务器设计，即使第一阶段只有一台爬虫服务器，也不需要后续重构执行模型。

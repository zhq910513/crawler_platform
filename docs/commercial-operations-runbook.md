# crawler_platform 1.0.2 商业化运维 Runbook

## 1. 首次部署失败

优先收集：`doctor.sh` 输出、`.env` 脱敏副本、`docker compose ps`、API 容器日志、MySQL/Redis 容器日志、磁盘和 inode 使用率。注意：宿主机 Python/npm 旧版本或缺失通常只是 WARNING，不应作为部署失败根因，发布检查应使用 Docker 工具容器。

处理顺序：

1. 环境体检：Docker、Compose、端口、磁盘、inode、SELinux、防火墙、时间同步。
2. 权限体检：当前用户、sudo 能力、Docker socket 权限、部署目录写权限。
3. 网络体检：国内镜像源、Docker Hub 拉取、pip/npm/apt/apk 源。
4. 服务体检：MySQL/Redis 是否健康，API `/health` 是否返回版本。
5. 迁移体检：Alembic head 是否唯一，MySQL 标识符是否超过 64 字符。

不可直接手工改数据库结构；必须先确认迁移脚本和发布版本。


## 1.1 宿主机旧版本兼容原则

客户服务器只要求满足最低部署条件：bash、Docker daemon 可用、Docker Compose 可用、当前用户有 Docker 权限和部署目录写权限。Python、pip、npm、node、curl、git、jq、ss/netstat、timedatectl 都是可选工具；缺失时预检只提示 WARNING，后续流程通过工具容器或降级逻辑处理。

不要用 `python3 -m compileall backend agent` 直接判断平台代码是否可上线。客户宿主机可能是 Python 3.6 或更旧版本，而平台后端/Agent 在 Python 3.12 容器内运行。正确检查命令是：`deploy/scripts/container-compile-check.sh` 或 `deploy/scripts/commercial-release-gate.sh`。

## 2. Agent 离线或不可调度

前端服务器列表先看：健康状态、容量状态、最近心跳、Docker 状态、docker.sock、项目目录可写、lastError。

常见判断：

- 最近心跳超时：检查 Agent 进程、网络、防火墙、平台地址和 Agent token。
- Docker 不可用：检查 Docker daemon、当前用户 Docker 权限、docker.sock 挂载。
- 可用槽位为 0：检查运行容器数量、maxContainerSlots、资源模板和任务并发。
- 磁盘或 inode 高水位：先清理日志、构建缓存、无用镜像，再恢复调度。
- 项目目录不可写：检查部署目录 owner、group、ACL、挂载路径。

## 3. 任务运行失败

任务详情页按以下顺序排查：

1. 生命周期事件：确认失败阶段是平台、Agent、Docker、爬虫代码、目标网站还是数据库。
2. 诊断卡片：查看 `failedStage`、`errorType`、`retryable`、`errorSummary`。
3. 日志尾部：优先过滤 `ERROR`、`WARNING` 或关键业务词。
4. Agent 资源快照：确认失败时 CPU/内存/磁盘/槽位/Docker 是否异常。
5. 下载完整日志：提供给研发或售后，不要直接截屏代替日志。

如果是 `LOST`，优先检查 Agent 心跳和 lease 过期；如果是 `WAITING_RESOURCE`，优先检查路由原因和资源锁。

## 4. 操作日志膨胀

`sys_operation_log` 只应记录用户操作和关键管理动作。Agent 心跳、领取任务、运行心跳、结果、事件、日志分片和日志完成上报不得写入该表。

发现膨胀时检查：

- `HIGH_FREQUENCY_AUDIT_PREFIXES` 是否包含新增 Agent 高频接口。
- 是否有业务服务重复写语义日志和中间件请求日志。
- 是否把任务日志误写入 `sys_operation_log`。

## 5. 升级和回滚

升级前：备份数据库、记录镜像 digest、记录 `.env` 脱敏副本、确认 Alembic 当前版本。

升级后：检查 `/health` 版本、Alembic head、admin 登录、公司/Agent/项目/任务/历史运行记录、日志 V2 查询。

回滚优先级：

1. 代码和镜像回滚。
2. 配置回滚。
3. 数据库迁移若不可逆，必须使用升级前备份恢复，不能手工降表。

## 6. 售后交付包最小材料

- 环境体检输出。
- 商业发布门禁结果。
- smoke-test 结果。
- 失败任务 runId 和日志下载文件。
- Agent lastError 和最近心跳时间。
- API `/health` 结果和平台版本。

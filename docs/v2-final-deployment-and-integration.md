# V2 最终部署与联调说明

## 1. 最终组件

V2 由三个组件组成：

```text
crawler_platform
    管理平台、权限、调度、发布、任务状态、日志、SSE、告警

crawler_agent
    安装在爬虫服务器，主动连接平台，启动和监控任务容器

crawler_platform_spiders
    爬虫执行镜像，一个 TaskRun 一个容器，内部调用 run(context)
```

## 2. 跨服务器通信

平台不连接爬虫服务器。所有通信由 Agent 主动发起：

```text
Agent → Platform /api/agent/v2/register
Agent → Platform /api/agent/v2/heartbeat
Agent → Platform /api/agent/v2/claim
Agent → Platform /api/agent/v2/runs/{run_id}/logs
Agent → Platform /api/agent/v2/runs/{run_id}/events
Agent → Platform /api/agent/v2/runs/{run_id}/finish
```

因此平台服务器不需要 SSH 到爬虫服务器，也不需要挂载远程 Docker Socket。

## 3. 生产升级顺序

1. 备份平台 MySQL 和 `.env`。
2. 部署新版 `crawler_platform`。
3. 执行 Alembic 迁移。
4. 启动 API、Scheduler、Maintenance、Web。
5. 在爬虫服务器安装或升级 Agent。
6. 构建并导入 `crawler_platform_spiders` SpiderRelease。
7. 为项目绑定公司成员、资源、密钥和发布通道。
8. 运行 `system.health` 任务测试完整链路。
9. 迁移真实爬虫任务。

## 4. 推荐联调用例

### 4.1 Agent 在线

确认 Agent 页面显示：

- 在线
- 协议版本 2.0
- 可用槽位
- CPU、内存、磁盘
- capabilities 和 labels

### 4.2 SpiderRelease 导入

导入 `crawler_platform_spiders` 镜像的 `RELEASE_MANIFEST.json` 后，确认发布页出现 `system.health` 入口。

### 4.3 成功任务

创建绑定 `system.health` 的任务，手动运行。预期：

```text
QUEUED → ASSIGNED → STARTING → RUNNING → SUCCEEDED
```

### 4.4 实时 ERROR

运行会主动抛错或记录 ERROR 的测试任务。预期：

- TaskRun 详情页实时显示最近错误。
- 日志窗口同步出现 ERROR。
- 终态显示 terminal_error。
- Agent 断网恢复后不会重复事件。

### 4.5 超时与取消

运行长时间任务并执行取消或设置短超时。预期：

```text
RUNNING → CANCEL_REQUESTED → CANCELLED/TIMED_OUT
```

### 4.6 Agent 重启恢复

任务运行中重启 Agent。预期：

- Agent 找回本地运行目录。
- 找回仍运行的容器或正确报告容器缺失。
- 日志不重复上传。
- 最终结果能补传平台。

## 5. 验证命令

平台服务：

```bash
docker compose ps && docker compose logs -f api scheduler maintenance web
```

Agent 服务：

```bash
systemctl status crawler-agent && journalctl -u crawler-agent -f
```

平台健康：

```bash
curl -fsS http://127.0.0.1:8080/health
```

Agent 本地运行目录：

```bash
find /var/lib/crawler-agent/runs -maxdepth 2 -type f | sort | tail -100
```

## 6. 关键安全约束

- 生产环境使用 HTTPS，Agent 不应使用明文公网 HTTP。
- Agent Token 和 Bootstrap Token 只能存在 Agent 本地 `.env`。
- 平台只向任务下发当前项目所需的最小资源与密钥。
- 爬虫容器不应持有平台用户 Token 或平台数据库连接。
- 普通项目成员不能查看密钥明文。
- 任务参数不能指定宿主机任意 Volume、Shell 命令或 Python 模块路径。

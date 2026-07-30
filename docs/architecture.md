# crawler_platform V2 架构说明

V2 是面向多公司、多项目的分布式爬虫管理平台。平台只做控制面，爬虫任务由远端 Agent 启动临时容器执行。

```text
浏览器前端
    ↓
crawler_platform API / Scheduler / Maintenance
    ↓ HTTPS，Agent 主动连接
crawler_agent 爬虫服务器执行代理
    ↓ Docker
crawler_platform_spiders 临时任务容器
    ↓
具体爬虫代码完成登录、翻页、解析、入库
```

## 组件职责

### crawler_platform

- 用户、公司、项目和项目成员权限。
- SpiderRelease、SpiderEntry、发布通道和回滚。
- 任务定义、调度、重试、取消和状态机。
- Agent 注册、心跳、槽位和运行租约。
- 日志、ERROR 事件、最近错误、最终错误和 SSE 前端推送。
- 资源绑定和最小资源清单生成。

### crawler_agent

- 安装在爬虫服务器。
- 主动向平台注册、心跳和认领任务。
- 本地创建 TaskRun 目录，写入 `task.json/resources.json/secrets.json`。
- 拉取不可变镜像摘要并启动 Docker 容器。
- 采集 stdout/stderr、结构化 ERROR、result.json。
- 本地 Spool、断网补传、Agent 重启恢复。
- 识别超时、取消、OOM、容器缺失和非零退出码。

### crawler_platform_spiders

- 固定爬虫执行项目。
- 只接收本地 `/run/crawler` 文件，不连接平台。
- 调用已注册的 `run(context) -> TaskResult`。
- 输出标准日志、ERROR 事件、`result.json`、`last_error.json`。

## 关键边界

- 平台服务器不连接业务数据库，也不保存采集业务数据。
- 平台服务器不访问爬虫服务器 Docker Socket。
- Agent 不需要平台反向连接，适合跨服务器和跨网络部署。
- 爬虫容器不持有平台 Token，不直接回调平台。
- 一个 TaskRun 只执行一次，失败重试会创建新的 TaskRun。
- 任务不能指定任意 Python 模块、函数、Shell 命令或宿主机 Volume。

## 数据流

```text
Scheduler 创建 QUEUED TaskRun
→ Agent claim 获得 lease_token
→ Agent 上报 STARTING/RUNNING
→ Agent 上传 logs/events
→ Platform 更新 last_error 并 SSE 推送
→ Agent 上传 finish/result
→ Platform 写入终态和 terminal_error
```

## 实时错误

爬虫内部发生登录失败、请求失败、数据库失败或未捕获异常时，`crawler_platform_spiders` 会输出结构化 ERROR。Agent 解析后实时上传平台，平台写入 `crawler_task_run_event` 并更新 `crawler_task_run.last_error_*` 字段。前端运行详情页通过 SSE 接收即时更新。


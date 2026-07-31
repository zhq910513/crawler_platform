# 爬虫项目一键接入说明

1. 在平台“公司配置”中生成公司级项目接入凭证 `CRAWLER_PLATFORM_DISCOVERY_TOKEN`。
2. 复制 `.env.example` 为 `.env`，填写平台地址、公司编号、服务器编码、镜像仓库和 discovery token。
3. 项目 `sch.py` 只用于本地执行和声明 `TASKS` 任务清单；生产调度由平台任务调度控制。
4. 每次构建完成执行：`./deploy/bootstrap.sh --non-interactive`。
5. 脚本会向 `/api/v1/discovered-projects` 上报 manifest、镜像 digest、部署服务器和任务定义，不会创建或覆盖生产 Cron。


## 业务镜像运行时要求

生产任务不会执行 `sch.py`，Agent 会在容器内执行：

`python -m crawler_runtime --entrypoint 包.模块:函数 --kwargs-json '{...}'`

因此每个爬虫业务镜像必须安装 `crawler-runtime`。本模板已提供 `runtime/` 目录和 `Dockerfile.example`，新项目可直接复制为 `Dockerfile`。

`sch.py` 只允许静态声明 `TASKS = [...]`，bootstrap 采用 AST 静态解析，不会 import 或执行 `sch.py`。严禁在 `sch.py` 模块加载阶段连接数据库、启动浏览器、启动调度器或执行无限循环。

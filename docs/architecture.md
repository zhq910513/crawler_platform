# 架构说明

```text
CI/CD
  └─ 构建并推送爬虫镜像
       └─ 登记镜像摘要到管理平台

管理平台 Docker Compose
  ├─ web         Vue + Nginx
  ├─ api         FastAPI
  ├─ scheduler   Cron、重试、超时、租约回收
  ├─ worker      日志和性能数据清理
  ├─ mysql       控制数据
  └─ redis       调度器锁和短期状态

爬虫服务器
  ├─ Docker Engine
  ├─ Host Agent
  └─ 临时爬虫容器
       └─ 直接写入业务数据库
```

管理平台与爬虫数据边界：

- 管理平台不保存采集业务数据。
- 管理平台不连接业务数据库。
- 管理平台不安装爬虫 Python 环境。
- 管理平台只发送镜像、命令、参数和密钥。
- Agent 主动出站连接平台，不使用 SSH。

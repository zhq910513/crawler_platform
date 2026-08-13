# crawler_platform 1.0.1 发布说明

## 版本定位

1.0.1 是 crawler_platform 1.0 的测试服与宿主机兼容性修复版，不新增业务功能，重点修复零数据部署、Agent 任务执行闭环、不同宿主机兼容性、诊断日志和 smoke-test 稳定性问题。

## 本轮测试暴露的问题

### 1. 前端构建问题

测试服宿主机没有 npm，必须通过 Node 工具容器构建前端。构建过程中发现 package-lock.json 与 package.json 不一致，导致 npm ci 失败；同时 index.html 仍引用 /src/main.js，而实际入口是 /src/main.ts；第三方类型定义也会在 vue-tsc 阶段触发类型检查失败。

### 2. MySQL 初始化兼容问题

零数据迁移时，部分外键约束名超过 MySQL 64 字符限制，导致 Alembic 初始化失败。1.0.1 要求所有迁移标识符必须控制在 MySQL 限制内。

### 3. 版本号残留问题

测试服曾出现 /health 返回旧版本号的情况，原因是 .env、agent env、Docker 镜像 tag、代码默认版本未统一。1.0.1 已统一版本号为 1.0.1。

### 4. CentOS 7 / 老宿主机兼容问题

测试服宿主机 Python 为 3.6，不能运行部分新语法或新参数，例如 subprocess.run(text=True)。部署、验收和 smoke-test 脚本必须避免依赖宿主机新版本 Python、npm、jq 等组件。

### 5. Agent 镜像缺 Docker CLI

Agent 通过 Docker SDK 可以访问 docker.sock，但容器内缺 Docker CLI，不利于启动期自检和线上排障。1.0.1 的 Agent 镜像已内置 Docker CLI。

### 6. Agent 任务线程异常静默

原 Agent 主循环没有正式日志，任务 future 异常不会打印，lastError 长期为空；docker_runner 中执行异常和 finish 回传异常也可能被吞掉，导致任务卡住时无法定位。1.0.1 增加正式 logging、future 异常记录、lastError 回传和关键执行阶段日志。

### 7. 快速任务状态机问题

测试中发现任务容器实际已经执行成功，result_payload、finished_at 已写入数据库，但 run_status 仍停在 STARTING。根因是快速任务在 Agent 第二次 heartbeat 推进到 RUNNING 前就完成并回传 SUCCEEDED，而后端状态机未允许 STARTING 直接进入终态。1.0.1 已允许 STARTING 进入 SUCCEEDED、PARTIAL_SUCCESS、FAILED、TIMED_OUT、CANCELLED 等终态，并在任务容器创建后立即 run heartbeat，降低快速任务状态滞留风险。

### 8. web/nginx 旧 upstream IP 问题

API 容器重建后，web/nginx 可能仍代理旧 API 容器 IP，导致 /health 通过 web 返回 502，而 API 容器自身健康检查正常。1.0.1 调整 nginx 配置使用 Docker DNS 动态解析，并建议后续部署链路中重建 API 后同步重启 web。

### 9. 测试环境配置污染问题

后端契约测试原来可能读取项目根目录真实 .env，导致测试登录账号密码与测试服真实 ADMIN_PASSWORD 不一致，从而批量返回 401。1.0.1 已在测试用例中显式覆盖测试数据库、Redis、管理员密码、JWT 密钥和加密密钥，保证测试环境与真实部署配置隔离。

## 1.0.1 主要修复

- 统一 APP_VERSION、PLATFORM_IMAGE_TAG、AGENT_VERSION、Python 包版本、前端 package 版本为 1.0.1。
- Agent Dockerfile 内置 Docker CLI。
- Agent 增加正式 logging，替代临时 print 诊断。
- Agent 主循环增加异常保护，避免单次 API 或线程异常拖垮主循环。
- Agent worker future 完成后检查异常并记录 lastError。
- Agent 任务容器创建后立即发送 run heartbeat。
- Agent pull、container create、container exit、finish callback 等关键阶段增加日志。
- 后端状态机允许 STARTING 直接进入终态，兼容极短任务。
- smoke-test 兼容 Python 3.6，避免使用 subprocess.run(text=True)。
- 新增 backend/requirements-test.txt，测试依赖与生产依赖分离。
- 新增 deploy/scripts/run-backend-tests.sh，使用独立 Python 测试容器运行后端契约测试，避免污染生产镜像。
- 后端契约测试强制覆盖测试配置，避免读取真实 .env。
- frontend nginx 使用 Docker DNS resolver 动态解析 api upstream。
- 1.0.1 已在测试服通过端到端 smoke-test：QUEUED -> RUNNING -> SUCCEEDED。
- 后端契约测试已通过：15 passed。

## 测试服验证结果

已验证：

- /health 返回 1.0.1。
- web/nginx 正常代理 API。
- Agent 能心跳上线。
- Agent 能领取平台任务。
- Agent 能拉取 smoke 爬虫镜像 digest。
- Agent 能创建独立任务容器。
- smoke 任务能执行并回传 result_payload。
- run 状态能从 QUEUED 进入 RUNNING 并最终 SUCCEEDED。

## 后续上线注意事项

- 不要提交 .env、.env.bak、data/mysql、data/redis 等测试服本地数据和密钥。
- 生产部署前必须重新生成 JWT_SECRET、SECRET_ENCRYPTION_KEY、数据库密码、Redis 密码和 CICD_TOKEN。
- 新增迁移前必须检查 MySQL 标识符长度。
- 后续如果单独重建 api，建议同步重启 web，或确认 nginx 动态解析配置已经构建生效。
- Agent 运行必须挂载 /var/run/docker.sock，并确保当前 Docker daemon 可用。

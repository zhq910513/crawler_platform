# 爬虫平台生产上线候选包审计记录 v1.0.79

## 结论

v1.0.79 是在 v1.0.78 运行契约修复基础上的上线候选整改版，目标是清理发布包风险、统一发布版本并补充发布前可自动化检查。

当前代码级、契约级测试可以证明：平台后端、Agent 下发 payload、DockerRunner 环境变量注入与 crawler_runtime 配置读取之间的关键契约已经闭环。生产上线前仍必须在真实服务器完成 Docker Compose、MySQL、Redis、Agent 节点、爬虫镜像拉取和真实任务执行的端到端验证。

## 本轮修复

1. 删除发布包中的本地开发数据库文件 `crawler_platform_dev.db`，避免把开发用户、会话、Join Token、操作日志等数据打入生产交付物。
2. `.gitignore` 增加 `*.db`、`*.sqlite`、`*.sqlite3`，降低后续再次误打包本地数据库的风险。
3. 同步平台发布版本为 `1.0.79`：
   - `VERSION`
   - `.env.example` 的 `APP_VERSION` / `PLATFORM_IMAGE_TAG`
   - `docker-compose.yml` 的 API / Web 镜像 tag 默认值
   - `docker-compose.yml` 的前端构建参数 `APP_VERSION` 默认值
   - `frontend/package.json`
   - `frontend/package-lock.json`
   - 单机部署脚本兜底版本
4. 新增发布包卫生测试，防止开发数据库、版本残留和缺失 ignore 规则再次回归。

## 本轮未强改内容

1. 没有修改数据库、Redis、OSS、账号中心、飞书或任何外部依赖客户端的调用契约。
2. 没有虚构生产环境连接信息、镜像仓库地址、Agent 节点或爬虫项目运行结果。
3. 没有把任务容器的 Agent Token 方案升级为 per-run runtime token。该项仍建议进入后续安全加固版本，因为需要后端鉴权模型、Agent 兼容策略和 runtime 接口一起设计。
4. 没有改动爬虫项目业务代码。平台正式上线前，应至少用一个真实爬虫项目镜像完成端到端运行验证。

## 上线前必须在真实环境验证

- `docker compose build`
- `docker compose up -d`
- `python -m app.migration_main`
- `/api/v1/health`
- 前端页面访问与静态资源版本
- 管理员登录
- 公司资源配置保存与查询
- 爬虫项目发布注册
- 正式任务创建
- Agent 注册、心跳、任务认领
- Agent 拉取真实 spider image
- 任务容器启动并执行 `python -m crawler_runtime`
- `context.config` / `context.accounts` 读取平台绑定
- 任务日志回传
- 账号状态上报
- 凭据租约申请与释放
- 任务成功、失败、取消、超时场景

## 本地验证结果

详见 `docs/release-verification-1.0.79.md`。本地已通过 Python 语法编译、104 个后端测试的文件级隔离执行、版本一致性检查和新增发布包卫生测试。

当前容器中，单进程完整后端 pytest 仍会超时，前端 `npm ci` 因依赖安装未完成导致 `npm run build` 无法完成。因此 v1.0.79 仍不能被描述为“生产已验证通过”，只能作为测试服/准生产联调候选包。

## 风险评级

- 本地代码级上线阻断项：已清理。
- 真实部署环境阻断项：仍需测试服或准生产环境验证。
- 生产安全加固项：任务容器最小权限 token 尚未完成。


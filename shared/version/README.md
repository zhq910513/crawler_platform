# crawler_platform 公共版本契约

`crawler_platform` 是一个单体交付仓库，前端、后端、Agent、部署脚本必须共享同一个发布版本。当前版本契约如下：

1. 发布版本解析优先级：Git tag > 最新 commit message > 根目录 `VERSION`。
2. `deploy/scripts/lib/version.sh` 是发布脚本的公共版本模块。
3. `deploy/scripts/sync-runtime-version.sh` 将解析出的发布版本同步到 `.env` 和 `.release/version.json`。
4. 后端通过 `backend/app/version.py` 读取 `APP_VERSION / APP_GIT_COMMIT / APP_BUILD_TIME`。
5. Agent 通过 `agent/crawler_agent/version.py` 读取 `AGENT_AGENT_VERSION / AGENT_GIT_COMMIT / AGENT_BUILD_TIME`，同时兼容 `APP_*`。
6. 前端通过 Docker build args 注入 `VITE_APP_VERSION / VITE_APP_GIT_COMMIT / VITE_APP_BUILD_TIME`，并生成 `/version.json`。

正式发布时以运行元数据为准：

- 后端：`/health`
- 前端：`/version.json`
- 数据库：`/health.data.migrationVersion`

源码中的 `VERSION` 和 `frontend/package.json` 是无 Git 上下文时的 fallback / package baseline，不能作为生产运行版本的唯一依据。

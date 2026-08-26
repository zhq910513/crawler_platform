# Release Notes v1.0.104

## 目标

修复远程自动部署因部署目录下运行期 `data/` 目录显示为 `?? data/` 而停止的问题。

## 改动

- `.gitignore` 统一忽略 `data/` 运行期持久化目录。
- 新增 Git 本地 exclude 自愈函数 `cp_git_ensure_runtime_excludes`。
- `remote-auto-deploy.sh` 在工作区状态检查前自动写入运行期目录忽略规则。
- GitHub Actions SSH 部署脚本在调用远程部署入口前也写入相同忽略规则，用于解决远程旧脚本尚未更新时的引导问题。
- 增加回归测试，确保 `data/project-builds/**` 不再污染远程 Git 工作区。

## 边界

- 不会自动删除 `data/`，避免误删数据库、构建缓存、任务日志等运行期数据。
- 真实源码改动仍会阻断自动部署。

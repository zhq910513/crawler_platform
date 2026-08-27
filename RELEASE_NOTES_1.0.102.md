# v1.0.102

## 修复

- 修复远程自动部署时运行期 `data/` 目录被 Git 工作区洁净检查误判为源码改动，导致部署因 `?? data/` 被阻断的问题。
- 自动在 `.git/info/exclude` 注册 `data/`、`.release/`、`agent/state.json`、`crawler_agent.env` 等运行期路径，兼容服务器上旧版 `remote-auto-deploy.sh` 在切换到新版前的检查。
- 更新 GitHub Actions SSH 部署入口：调用远程部署脚本前先忽略运行期目录，仅对真实源码改动继续阻断。
- `.gitignore` 增加 `data/project-builds/*`，避免平台构建中心本地构建目录污染部署工作区。

## 边界

- 仍然会阻断真实源码文件改动、删除、未跟踪源码文件和本地未推送提交。
- 不会删除或覆盖运行期 `data/` 目录。

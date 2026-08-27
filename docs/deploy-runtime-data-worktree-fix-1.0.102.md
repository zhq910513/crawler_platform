# v1.0.102 远程部署运行期目录洁净检查修复

## 背景

平台构建中心会在部署目录下创建运行期目录，例如 `data/project-builds`。远程自动部署入口在执行 `remote-auto-deploy.sh` 前会检查 Git 工作区是否干净。旧逻辑把 `?? data/` 当成真实未提交改动，导致自动部署停止。

## 处理方式

v1.0.102 将运行期目录纳入部署工作区过滤：

- `data/`
- `.release/`
- `agent/state.json`
- `crawler_agent.env`

部署入口会先写入 `.git/info/exclude`，以便兼容服务器上尚未升级的旧版远程部署脚本；新版 `remote-auto-deploy.sh` 也会在内部再次注册 exclude，并使用 `cp_git_status_deploy_relevant` 只检查真实源码改动。

## 保留的安全门禁

以下情况仍会阻断部署：

- Git 管理文件存在内容改动。
- Git 管理文件被删除。
- 出现未跟踪源码文件。
- 本地分支存在未推送提交。

运行期目录不会参与源码洁净判断，也不会被自动删除。

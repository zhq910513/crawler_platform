# 远程自动部署运行期目录自愈 v1.0.104

## 背景

平台控制端部署目录会生成 `data/` 下的运行期持久化目录，例如 MySQL、Redis、任务日志、项目构建缓存和源码缓存。这些目录属于部署运行状态，不属于代码版本事实。

旧部署入口在拉取新版本前执行 `git status --porcelain`，当远程目录出现 `?? data/` 时会误判为真实未提交改动并阻断自动部署。

## 改动

- `.gitignore` 改为整体忽略 `data/` 运行期目录。
- 新增 `cp_git_ensure_runtime_excludes`，在远程部署入口写入 `.git/info/exclude`，本地忽略运行期目录。
- GitHub Actions SSH 部署脚本在调用远程旧版 `remote-auto-deploy.sh` 前先写入 runtime excludes，解决旧脚本无法自我更新的引导问题。
- `remote-auto-deploy.sh` 在执行工作区干净检查前主动应用 runtime excludes。
- 发布包不再携带空的 `data/` 运行期目录；目录由部署脚本按需创建。

## 边界

- 只自动忽略平台受控运行期目录，不会忽略任意未知源码改动。
- 如果远程工作区存在真实代码内容修改、删除或未纳入运行期白名单的未跟踪文件，仍会阻断部署。

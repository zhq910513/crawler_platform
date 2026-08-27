# Release Notes v1.0.105

## 目标
修复远程自动部署仍被运行期 `data/` 目录阻断的问题。

## 变更
- 修复 `.git/info/exclude` 已存在旧 marker 但内容不完整时不会补齐 `/data/` 的问题。
- 新增部署工作区状态过滤函数，脏工作区判断默认忽略运行期目录：`data/`、`.release/`、`frontend/node_modules/`、`frontend/dist/`、`agent/state.json`、`agent/.env.local`、`crawler_agent.env`。
- `remote-auto-deploy.sh` 失败时只打印真实阻断项，不再把运行期目录作为未提交改动输出。
- GitHub Actions SSH 部署入口在远程脚本执行前修复旧 exclude block，并使用同样的运行期目录过滤逻辑。

## 边界
真实代码内容改动、删除、非运行期未跟踪文件仍会阻断自动部署。

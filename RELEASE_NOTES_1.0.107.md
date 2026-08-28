# Release Notes v1.0.107

## 修复

- 修复 GitHub Actions `Deploy server by SSH` 在 `appleboy/ssh-action@v1.2.0` 下启用 `script_stop: true` 后破坏远端 HEREDOC / `if` 脚本结构，导致 `bash: -c: ... syntax error near unexpected token `;'` 的问题。
- 移除冗余 `script_stop`，继续由内联脚本首行 `set -Eeuo pipefail` 提供失败即退出语义，不改变现有远程部署业务流程。
- 在 CI/CD 工作区契约检查和现有远程部署回归测试中加入 `script_stop` 禁止项，防止同类 quoting/脚本重写问题再次进入发布树。

## 保留契约

- 保留 v1.0.106 的 `.git/info/exclude` 运行数据 bootstrap、`filtered_status`、权限位自愈和 `remote-auto-deploy.sh` 调用顺序。
- 保留真实源码修改、删除、暂存修改和未知未跟踪文件阻断自动部署的安全边界。
- 不修改构建中心源码 bundle/cache 契约，不重新引入已废弃的 upload/cache-dir 兼容字段。

## 失败证据

- v1.0.106 商业发布门禁通过后进入 SSH 部署任务。
- SSH action 将脚本下发到远端后，在真正执行 `remote-auto-deploy.sh` 前由 Bash 解析失败：`syntax error near unexpected token `;'`。
- 同一内联脚本脱离 `script_stop` 重写后可通过 `bash -n`。

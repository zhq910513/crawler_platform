# SSH Action Script Parsing Fix v1.0.107

## Root cause

`.github/workflows/deploy-test-server.yml` 使用 `appleboy/ssh-action@v1.2.0`，同时配置 `script_stop: true`。该选项会对多行远端脚本做额外处理，与当前 bootstrap 中的 HEREDOC、函数和 `if` 结构冲突，导致远端 Bash 在进入仓库内 `remote-auto-deploy.sh` 之前就解析失败。

当前脚本首行已经是：

```bash
set -Eeuo pipefail
```

因此失败即退出语义并不依赖 `script_stop`。v1.0.107 删除该选项，保持其余部署脚本原样。

## Regression guard

- `deploy/scripts/check-deploy-worktree-contract.py` 明确拒绝 workflow 再次出现 `script_stop:`。
- `backend/tests/test_remote_deploy_runtime_data_ignore_10104.py` 同步验证这一契约。
- workflow 中的 runtime-data bootstrap、filtered dirty-worktree gate 和最终 `remote-auto-deploy.sh` 调用顺序不变。

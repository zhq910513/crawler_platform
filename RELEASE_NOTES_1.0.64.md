# 1.0.64 CI/CD 工作区权限位漂移自愈专项

## 背景

服务器部署目录全部通过 CI/CD 更新，但历史部署脚本会对 Git 管理下的 `deploy/scripts/*.sh` 执行 `chmod +x`。如果仓库中脚本记录为 `100644`，部署后会在服务器工作区留下仅文件权限位变化：

```text
old mode 100644
new mode 100755
```

下一次 GitHub Actions 进入服务器时，部署前门禁会看到 `git status --porcelain` 非空并阻断部署。

## 本次调整

1. `remote-auto-deploy.sh` 部署入口增加权限位漂移自愈：
   - 仅权限位变化、文件内容与 HEAD 一致时自动恢复。
   - 内容改动、删除、未跟踪文件仍然阻断部署。
   - 不使用 `git reset --hard` 清理工作区，避免覆盖线上真实补丁。
2. `cp_fix_project_permissions` 不再 `chmod +x` Git 管理脚本。
3. 部署脚本内部调用统一改为 `bash deploy/scripts/xxx.sh`，不再依赖脚本可执行位。
4. GitHub Actions 远程部署入口判断从 `-x` 调整为 `-f`，避免脚本存在但不可执行时误走兼容分支。
5. 新增 `check-deploy-worktree-contract.py`，纳入商业发布门禁。
6. 补充后端契约测试，防止后续重新引入全局 chmod 或一刀切脏工作区阻断。

## 预期效果

后续如果服务器上仅出现类似：

```text
M deploy/scripts/prepare-agent-image.sh
```

且差异只有 `old mode/new mode`，CI/CD 会自动恢复权限位并继续部署。若存在真实代码内容改动，仍然阻断并提示人工确认。

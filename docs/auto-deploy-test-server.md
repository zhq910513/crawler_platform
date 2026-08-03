# 测试服自动部署说明

目标：本地提交并 push 到 `main` 后，GitHub Actions 自动执行商业发布门禁，门禁通过后通过 SSH 登录测试服，并调用项目内标准脚本完成部署。

## 设计原则

- GitHub Actions 只负责触发、门禁和远程编排。
- 真正发布逻辑仍在项目内脚本：`deploy/scripts/release-upgrade.sh`。
- 测试服工作区必须干净；发现本地未提交改动或本地提交未推送时自动停止。
- 版本来自同一条公共解析链：Git tag > 最新 commit message > `VERSION`。

## GitHub Secrets

在仓库 Settings → Secrets and variables → Actions 中配置：

| Secret | 示例 | 说明 |
|---|---|---|
| `TEST_SERVER_HOST` | `1.2.3.4` | 测试服 IP 或域名 |
| `TEST_SERVER_USER` | `deploy` | SSH 用户，测试期可用 root，商业交付建议 deploy 用户 |
| `TEST_SERVER_SSH_KEY` | 私钥内容 | 只给测试服部署权限 |
| `TEST_SERVER_PORT` | `22` | SSH 端口 |
| `TEST_SERVER_PROJECT_DIR` | `/data/projects/crawler_platform` | 测试服项目目录 |

## 推送触发

```bash
git add -A && git commit -m "自动部署优化v1.0.6" && git push origin main
```

GitHub Actions 会执行：

1. `commercial-release-gate.sh`
2. SSH 到测试服
3. `remote-auto-deploy.sh`
4. `release-upgrade.sh`
5. 校验 `/health` 和 `/version.json`

成功日志应包含：

```text
RELEASE_GATE=PASS
RELEASE_UPGRADE=PASS version=X.Y.Z
```

## 失败保护

自动部署会在以下情况停止：

- 测试服工作区有未提交改动。
- 测试服本地分支有未推送提交。
- GitHub 传入的 commit 不在 `origin/main` 上。
- 商业发布门禁失败。
- 数据库备份、迁移、构建、健康检查、前端版本校验失败。

## 生产环境建议

测试服可以 `push main` 自动部署；生产环境建议改为 `vX.Y.Z` tag 触发，并增加 GitHub Environment 人工审批。

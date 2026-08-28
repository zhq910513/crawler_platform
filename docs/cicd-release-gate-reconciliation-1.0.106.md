# CI/CD Release Gate Reconciliation v1.0.106

## 问题定位

v1.0.104 发布树中混入了三类与当前实现不一致的测试：重复副本、旧 source bundle/cache 设计测试，以及已经在发布说明中承诺但生产实现缺失的 Docker diagnostics 测试。发布门禁因此在后端 pytest 阶段失败，前端镜像虽然构建成功，最终仍由 `RELEASE_GATE=FAIL` 统一退出。

## 当前唯一源码获取契约

1. `git clone`。
2. `CRAWLER_PROJECT_SOURCE_BUNDLE_DIR` 下预置源码包。
3. GitHub 官方归档包。
4. `CRAWLER_PROJECT_SOURCE_CACHE_ROOT/<source-key>/` 目录缓存。

不支持也不声明 `crawler_project_source_bundle_upload_enabled`、`crawler_project_source_cache_dir` 和 `save_source_bundle()`。

## Docker diagnostics

启用 `CRAWLER_PROJECT_DOCKER_CONTEXT_DIAGNOSTICS_ENABLED=1` 后，构建任务写入 `DOCKER_CONTEXT` 日志，包含 Dockerfile 是否存在、基础镜像、上下文文件数和字节数。Docker Engine API 返回错误时，异常同时保留最近 stream tail 和最终错误信息。

## Remote deploy bootstrap

GitHub Actions SSH 入口在调用远端仓库内的部署脚本之前直接修复 `.git/info/exclude`。因此即使服务器仍运行旧版 `remote-auto-deploy.sh`，运行期目录也不会在升级到新脚本之前先触发 dirty-worktree 阻断。

新版 `host.sh` 同时提供：

- `cp_ensure_runtime_data_git_excludes`
- `cp_git_status_filtered`
- 既有 `cp_git_relevant_status` 契约

过滤只针对已知运行期的未跟踪路径；真实源码修改、删除、暂存修改和未知未跟踪文件继续阻断自动部署。

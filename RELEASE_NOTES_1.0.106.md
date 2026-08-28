# Release Notes v1.0.106

## 修复

- 修复商业发布门禁被跨版本、重复及已废弃源码缓存契约测试阻断的问题；删除逐字节重复测试和已经被 v1.0.104 当前实现替代的 `source_bundle_upload_enabled / source_cache_dir / <key>.tar.gz` 旧测试契约。
- 恢复 Docker Engine API 构建错误的上下文诊断：异常保留最近 Docker stream tail，不再只返回最后一条 `errorDetail`。
- 增加 Dockerfile 基础镜像解析与 `DOCKER_CONTEXT` 构建上下文日志；接入 `CRAWLER_PROJECT_DOCKER_CONTEXT_DIAGNOSTICS_ENABLED` 配置链路。
- 修复远程自动部署的旧版本 bootstrap 死锁：GitHub Actions SSH 入口会在执行服务器旧版部署脚本前修复 `.git/info/exclude`，运行期 `data/`、`.release/`、日志、前端构建产物及 Agent 本地状态不再被误判为源码改动。
- 远程工作区检查统一使用 `git status --porcelain -uall`，可准确显示真正阻断部署的未跟踪源码文件；已跟踪文件修改、删除和未知未跟踪源码仍会阻断部署。

## 保留的真实契约

- 构建中心源码包继续使用 `CRAWLER_PROJECT_SOURCE_BUNDLE_DIR` 预置 `zip/tar.gz/tgz` 文件。
- 源码缓存继续使用 `CRAWLER_PROJECT_SOURCE_CACHE_ROOT/<source-key>/` 目录结构。
- 未重新引入已经不属于当前实现的 `crawler_project_source_bundle_upload_enabled`、`crawler_project_source_cache_dir` 或 `save_source_bundle()` 伪兼容接口。
- 保留既有 `cp_git_relevant_status` 调用契约，并将其统一路由到新的 `cp_git_status_filtered` 实现。

## 验证

- Docker diagnostics / runtime deploy / version contract 定向回归：15 passed。
- 除 `test_rebuild_contract.py` 外后端测试：100 passed。
- `test_rebuild_contract.py` 按 CI 初始化契约执行：65 个测试全部通过；连同初始化测试该分片输出 67 passed。
- 当前后端唯一测试总数：165，全部覆盖通过。

# 平台构建中心最小发布闭环 v1.0.92

## 背景

v1.0.88-v1.0.91 已经把错误的“爬虫项目主动 CI/CD”方向纠正为“平台主动构建、爬虫项目被动提供构建契约”。v1.0.92 开始补平台构建中心的最小闭环。

## 闭环范围

本版本支持：

```text
项目发布页填写公司、节点、仓库、分支
→ 平台创建 Build Job
→ git clone 源码
→ 执行 scripts/platform_build_contract.sh
→ 读取 VERSION 作为不可变 releaseVersion
→ docker build
→ docker push
→ docker image inspect 读取 RepoDigest
→ 重新生成最终 crawler_manifest.json
→ 登记 CrawlerDiscoveredProject / CrawlerProjectRelease
→ 首次接入项目
→ 下发节点部署指令
```

## 契约边界

平台负责发布事实与构建执行，爬虫项目只提供：

```text
scripts/platform_build_contract.sh
scripts/sync_sch.py
scripts/validate_tasks.py
scripts/build_manifest.py
Dockerfile
VERSION
TASK_DEFINITION
```

爬虫项目不保存平台 Token、registry 密码，也不主动 POST 平台。

## 启用条件

默认关闭。启用需要配置：

```env
CRAWLER_PROJECT_BUILD_ENABLED=1
CRAWLER_PROJECT_IMAGE_REPOSITORY_PREFIX=42.193.226.138:5000/crawler_projects
CRAWLER_PROJECT_BUILD_ROOT=/data/project-builds
```

构建执行环境必须真实具备：

```text
git
docker CLI
Docker daemon/socket
目标 Git 仓库读取权限
目标 registry 推送权限
```

这些权限目前不由平台数据库管理。不能把它说成“凭据中心已完成”。

## 安全限制

- v1.0.92 不支持数据库化仓库读取凭据。
- v1.0.92 不支持数据库化镜像仓库推送凭据。
- v1.0.92 不支持异步构建队列。
- v1.0.92 不支持构建日志实时 SSE。
- 如果未启用或缺宿主能力，发布流水线继续 fail-closed。

## 后续版本建议

- v1.0.93：构建任务异步化和前端轮询构建状态。
- v1.0.95：代码仓库读取凭据模型。
- v1.0.95：镜像仓库推送凭据模型。
- v1.0.96：构建日志流式展示和取消构建。

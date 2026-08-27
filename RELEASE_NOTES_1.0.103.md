# v1.0.103

## 修复

- 修复远程自动部署被 `data/` 运行期目录阻断的问题：部署入口会在 Git 工作区检查前写入 `.git/info/exclude` 运行期忽略规则，`data/`、`.release/`、本地数据库文件不再阻断自动部署。
- 修复平台控制端访问 GitHub 长期不稳定时只有远程拉取路径的问题：构建中心新增已上传源码包兜底与源码缓存兜底。
- 修复 Docker Engine API 构建失败时错误信息缺少上下文的问题：保留最近 Docker stream tail，并在 Build Job 日志中输出 Docker context、Dockerfile 状态、基础镜像和上下文大小。
- 修复构建中心 readiness 对 `git` 命令的硬性阻断：当源码包、源码缓存或官方归档包兜底可用时，`git` 缺失不再直接阻断发布分析。

## 新增配置

- `CRAWLER_PROJECT_SOURCE_BUNDLE_UPLOAD_ENABLED=1`
- `CRAWLER_PROJECT_SOURCE_BUNDLE_DIR=/data/project-builds/source-bundles`
- `CRAWLER_PROJECT_SOURCE_CACHE_ENABLED=1`
- `CRAWLER_PROJECT_SOURCE_CACHE_DIR=/data/project-builds/source-cache`
- `CRAWLER_PROJECT_DOCKER_CONTEXT_DIAGNOSTICS_ENABLED=1`

## 新增接口

- `POST /api/v1/project-builds/source-bundles`

用于预置爬虫项目源码包。后续构建在 `git clone` / GitHub 归档包不可用时会自动使用对应 `repositoryUrl + refName` 的源码包。

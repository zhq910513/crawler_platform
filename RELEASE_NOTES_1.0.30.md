# crawler_platform 1.0.30 发布说明

## 版本

- crawler_platform：1.0.29 → 1.0.30

## 核心目标

1.0.30 聚焦爬虫项目自动构建镜像版本的接入体验：新增项目不再需要每个仓库重复配置一整套 CI 变量和密钥，改为“Git 组织/群组全局配置一次 + 单项目一键初始化 CI 文件”。

## 主要变更

- 新增公开 CI helper：`GET /api/v1/cicd/spider-release-register.py`。
- 新增公开初始化脚本：`GET /api/v1/cicd/spider-project-init.sh`。
- 新增 GitHub Actions 模板：`GET /api/v1/cicd/templates/github-actions-spider-release.yml`。
- 新增 GitLab CI 模板：`GET /api/v1/cicd/templates/gitlab-ci-spider-release.yml`。
- 新增平台侧 CI 一键初始化指南：`GET /api/v1/cicd/spider-projects/one-click-guide`。
- 项目页新增“CI一键初始化”入口，展示全局变量、全局密钥、项目初始化命令和模板内容。
- CI helper 仅静态解析 `crawler_manifest.json` 或 `sch.py` 的 `TASKS`，不 import 业务代码，避免构建阶段触发数据库、Redis、OSS、登录等外部依赖。
- Agent 职责保持不变：不拉 Git、不构建镜像，只拉取平台登记的 `imageRepository@sha256:digest`。

## Git 设置原则

- GitHub：优先使用 Organization Variables / Secrets；每个爬虫项目只提交统一 workflow 文件。
- GitLab：优先使用 Group CI/CD Variables；每个爬虫项目只提交统一 `.gitlab-ci.yml`。
- 项目差异默认从仓库名、`VERSION`、`sch.py` 或 `crawler_manifest.json` 推导。
- 不在平台中直接写远端 Git 仓库；当前代码没有 GitHub App、GitLab PAT 或 OAuth 写入契约，避免凭空增加高风险依赖。

## 数据库迁移

- 1.0.30 不新增数据库迁移文件。

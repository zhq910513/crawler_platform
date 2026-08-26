# v1.0.101

## 变更摘要

- 修复平台构建中心在控制端到 GitHub 的 `git clone` 长时间失败后只能阻断的问题。
- 新增 GitHub 源码归档包兜底：标准 GitHub 仓库在 `git clone` 多次失败后，会自动尝试 `codeload.github.com` 的 tar/zip 源码归档包。
- 源码归档包路径不依赖 git clone 协议；如果归档包可访问，平台可继续执行被动构建契约、Docker 构建、推送和 Release 登记。
- 归档包不含 `.git` 目录时，平台会从归档根目录提取提交标识；无法提取时使用 `archive-<ref>` 作为构建标识，避免构建流程因缺少 `.git` 中断。
- 发布页 Build Job 日志新增 `SOURCE_ARCHIVE` / `SOURCE_ARCHIVE_SKIP` 阶段，方便判断到底是 Git 协议失败，还是 GitHub/codeload HTTPS 出口都不可用。

## 新增配置

```env
CRAWLER_PROJECT_SOURCE_ARCHIVE_FALLBACK_ENABLED=1
CRAWLER_PROJECT_SOURCE_ARCHIVE_ATTEMPTS=1
CRAWLER_PROJECT_SOURCE_ARCHIVE_TIMEOUT_SECONDS=120
```

部署脚本会自动补齐这些配置。

## 边界说明

本版本不会内置第三方 GitHub 代理，避免供应链风险。如果控制端服务器到 `github.com` 和 `codeload.github.com` 都不可达，平台仍需要使用控制端可访问的 Git 镜像仓库地址。

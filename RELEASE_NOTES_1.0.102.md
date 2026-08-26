# v1.0.102 平台构建中心源码获取韧性增强

## 背景

控制端服务器访问 GitHub 出口不稳定时，单纯 `git clone` 重试和 GitHub 官方归档包兜底仍可能失败。平台需要在代码层提供更多源码获取路径，避免要求运维登录服务器手动放文件。

## 变更

- 新增源码镜像映射配置 `CRAWLER_PROJECT_SOURCE_MIRROR_MAP`，平台可在构建时自动优先尝试内网/国内 Git 镜像仓库。
- 新增源码包上传接口 `POST /api/v1/project-source-bundles`。
- 项目发布页构建失败后可上传 `zip/tar.gz/tgz` 源码包，再点击“重新构建”。
- 构建中心失败兜底顺序调整为：源码镜像映射 → git clone → GitHub 官方归档包 → 已上传源码包 → 最近成功源码缓存。
- 新增最近成功源码缓存，成功获取源码后自动刷新 `/data/project-builds/source-cache`，远端不可用时可兜底使用。
- 新增构建日志阶段：`CLONE_MIRROR`、`SOURCE_BUNDLE`、`SOURCE_BUNDLE_SKIP`、`SOURCE_CACHE`、`SOURCE_CACHE_SKIP`。

## 边界

- 平台不会内置不可信第三方 GitHub 代理。
- 如果没有源码镜像、没有已上传源码包、也没有历史成功缓存，并且 GitHub/codeload 全部不可达，则仍会失败。
- 使用缓存兜底时可能不是远端最新提交，构建日志会明确提示。

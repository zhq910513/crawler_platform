# crawler_platform 1.0.32

## 核心变化

- 将“平台访问地址”语义收敛为“控制端公网回调地址”。
- GitHub / GitLab 仓库不再要求配置 `CRAWLER_PLATFORM_URL`。
- CI 初始化脚本由平台动态生成，并把控制端回调地址固化进 workflow。
- workflow 统一使用 `CRAWLER_CONTROL_BASE_URL` 下载 helper 并注册 release。
- 新项目仓库只必须配置公司级 `CRAWLER_PLATFORM_DISCOVERY_TOKEN`。
- 保留旧 `platform.public_url` / `PLATFORM_PUBLIC_URL` / `CRAWLER_PLATFORM_URL` 兼容读取，但新文档和新模板不再推荐。

## 边界

- 平台不会直接修改 GitHub/GitLab 远端仓库；当前没有 GitHub App / GitLab PAT / OAuth 写入契约。
- Agent 仍只拉取平台登记的镜像 digest，不拉 Git、不构建镜像。
- 多服务器部署仍在平台页面选择，不写入 Git CI。

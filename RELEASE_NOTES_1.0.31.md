# crawler_platform 1.0.31 发布说明

## 版本

- crawler_platform：1.0.30 → 1.0.31

## 核心变化

1.0.31 适配个人 GitHub 账号混放多家公司爬虫项目的真实使用方式。CI 注册 release 时不再强依赖每仓库配置 companyId，推荐由仓库内非敏感 `crawler_project.json.companyCode` 声明项目归属公司，后端用公司级 Discovery Token 校验归属一致性。

## 主要改动

- `ProjectDiscoveryCreate.companyId` 改为可选；后端可通过 `manifest.companyCode` 解析公司。
- Discovery Token 校验改为：token 所属公司必须与 `companyCode` 解析出的公司一致。
- CI helper 新增 `crawler_project.json` 解析，支持 `companyCode / projectCode / projectName / releaseChannel`。
- GitHub Actions / GitLab CI 模板不再要求 `CRAWLER_PLATFORM_COMPANY_ID`。
- 初始化脚本新增生成 `crawler_project.json`，并要求传入 `CRAWLER_COMPANY_CODE`。
- CI 引导页面改为个人仓库友好模式，并说明多服务器部署由平台完成，不在 Git 配置里处理。

## 数据库

- 1.0.31 不新增数据库迁移文件。

# 爬虫项目自动构建镜像与注册 Release

## 目标

爬虫项目推送到 Git 后，由 Git CI 自动完成：

1. 构建 Docker 镜像；
2. 推送镜像仓库；
3. 获取 `sha256:digest`；
4. 回调爬虫平台控制端 API 注册 release；
5. 平台页面选择一个或多个执行节点一键部署；
6. 目标节点 Agent 拉取同一个 `imageRepository@sha256:digest`。

执行节点 Agent 不拉 Git、不构建镜像。

## 控制端公网回调地址

GitHub Actions / GitLab CI 需要访问平台 API 注册 release。这个地址在平台内统一叫：

```text
控制端公网回调地址
```

它通常就是你当前打开爬虫平台的公网 IP + 端口或域名，例如：

```text
http://1.2.3.4
https://crawler.example.com
```

从 1.0.34 开始，Git 仓库不需要手工配置控制端链接。控制端会在“CI一键初始化”里生成带回调地址的一行命令，初始化脚本会把该地址固化到 workflow 的 `CRAWLER_CONTROL_BASE_URL`。

如果平台处在 Nginx、SLB、CDN 或端口映射后面，建议在“系统设置 -> 控制端公网回调地址”里显式保存最终公网地址。

## 新项目初始化

在平台项目页点击“CI一键初始化”，复制生成的一行命令，例如：

```bash
curl -fsSL 'http://1.2.3.4/api/v1/cicd/spider-project-init.sh?provider=github&companyCode=ulike' | sh
```

该命令会在爬虫项目仓库根目录生成：

```text
crawler_project.json
.github/workflows/crawler-platform-spider-release.yml
VERSION
sch.py 示例
```

`crawler_project.json` 是非敏感文件，可以提交到 Git：

```json
{
  "companyCode": "ulike",
  "projectCode": "xhs_note_image",
  "projectName": "小红书笔记图片采集",
  "releaseChannel": "stable"
}
```

不同公司的项目都放在个人 GitHub 仓库时，必须用 `companyCode` 区分归属公司。

## GitHub 仓库配置

仓库只必须配置一个 Secret：

```text
CRAWLER_DISCOVERY_TOKEN
```

该 token 是公司级项目发现凭证。A 公司 token 不能注册 B 公司项目。

可选 Variables：

```text
CRAWLER_REGISTRY_HOST        默认 ghcr.io
CRAWLER_REGISTRY_NAMESPACE   默认 GitHub 用户名
CRAWLER_RELEASE_CHANNEL      默认 stable
```

GHCR 默认使用 workflow 的 `github.token` 推送；私有 registry 再配置：

```text
CRAWLER_REGISTRY_USERNAME
CRAWLER_REGISTRY_PASSWORD
```

## 多节点部署

CI 只构建和注册 release，不写执行节点列表。

同一个 release 要部署到多个执行节点时，在平台页面选择目标节点并一键部署。多个 Agent 会拉取同一个 digest 镜像。

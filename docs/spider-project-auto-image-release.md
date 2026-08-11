# 爬虫项目自动构建镜像发布

## 目标

新增爬虫项目后，平台不要求执行服务器登录 Git，也不要求客户服务器构建镜像。标准流程是：

```text
爬虫项目 push / tag
  -> GitHub Actions / GitLab CI 构建镜像
  -> 推送镜像仓库并取得 sha256 digest
  -> CI 注册平台 release
  -> 平台一键部署到一台或多台服务器
  -> 多个 Agent 各自拉取同一个 digest 镜像
```

## 适配个人 GitHub 混放多家公司项目

如果不同公司的项目都放在同一个个人 GitHub 账号下，不要把公司 ID 配成个人账号全局变量。

每个爬虫项目仓库根目录必须放非敏感归属文件：

```json
{
  "companyCode": "ulike",
  "projectCode": "xhs_note_image",
  "projectName": "小红书笔记图片采集",
  "releaseChannel": "stable"
}
```

平台后端会按以下规则校验：

```text
crawler_project.json.companyCode -> 平台公司
Discovery Token -> 该公司 token
二者必须匹配
```

当前版本仍然使用公司级 Discovery Token；没有新增全局多公司 token，也不会允许 A 公司 token 注册 B 公司项目。

## GitHub 仓库配置

个人仓库推荐每个项目仓库设置：

Variables：

```text
CRAWLER_PLATFORM_URL
CRAWLER_PLATFORM_REGISTRY_HOST=ghcr.io
CRAWLER_PLATFORM_REGISTRY_NAMESPACE=你的 GitHub 用户名
CRAWLER_PLATFORM_RELEASE_CHANNEL=stable
```

Secrets：

```text
CRAWLER_PLATFORM_DISCOVERY_TOKEN=该项目所属公司的 Discovery Token
```

GHCR 通常可以使用 GitHub Actions 自动提供的 `GITHUB_TOKEN` 推送包；私有或外部 registry 再补充：

```text
CRAWLER_REGISTRY_USERNAME
CRAWLER_REGISTRY_PASSWORD
```

## 单项目初始化

在爬虫项目仓库根目录执行：

```text
curl -fsSL https://你的爬虫平台访问地址/api/v1/cicd/spider-project-init.sh | CRAWLER_PLATFORM_URL=https://你的爬虫平台访问地址 CRAWLER_COMPANY_CODE=ulike sh -s -- github
```

GitLab 把最后的 `github` 改成 `gitlab`。

初始化脚本只生成：

```text
crawler_project.json
.github/workflows/crawler-platform-spider-release.yml 或 .gitlab-ci.yml
VERSION 示例
sch.py 示例
```

它不会提交代码，不会访问远端 Git 仓库，也不会写入 GitHub / GitLab secrets。

## 项目契约

仓库根目录至少需要：

```text
Dockerfile
VERSION
crawler_project.json
sch.py 或 crawler_manifest.json
```

`sch.py` 要使用静态 `TASKS = [...]`，CI helper 只做 AST 字面量解析，不 import 业务代码。

## 多服务器部署

同一家公司的项目需要部署到多台服务器时，不需要改 Git 配置。

```text
CI 构建一次 release digest
  -> 平台选择多台目标服务器
  -> 多台服务器 Agent 拉取同一个 imageRepository@sha256:digest
```

不要让每台服务器分别 git pull 或 docker build。

## 版本规则

每次发布必须递增 patch，例如：

```text
1.0.14 -> 1.0.15
```

禁止使用 `latest/main/dev` 作为平台 release 版本。

## Agent 职责

Agent 不拉 Git，不构建镜像，只拉取平台登记的：

```text
imageRepository@sha256:digest
```

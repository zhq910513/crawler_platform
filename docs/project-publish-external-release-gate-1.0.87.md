# 项目发布外部 Release 注册门禁 v1.0.87

## 背景

平台构建中心尚未形成闭环时，发布页不能把 Git 仓库地址直接推进到“构建成功”。缺少以下真实能力时必须阻断：

- 平台构建执行器
- 代码仓库读取凭据
- 镜像仓库推送凭据

## 正确路径

当前安全发布路径是外部 CI 注册 Release：

```text
crawler_platform_spiders 仓库
  ↓
外部 CI 构建镜像
  ↓
生成 crawler_manifest.json
  ↓
POST /api/v1/discovered-projects 注册 Release
  ↓
项目发布页匹配已登记版本
  ↓
部署到执行节点
```

## 本版行为

当发布页输入的仓库没有匹配到正式项目或已登记项目版本时，流水线返回：

```json
{
  "blockedReasonCode": "PLATFORM_BUILD_CENTER_NOT_READY",
  "mode": "EXTERNAL_RELEASE_REQUIRED",
  "supportedReleasePath": "EXTERNAL_CI_RELEASE_REGISTRATION"
}
```

这表示不是节点问题，也不是仓库 URL 格式问题，而是当前仓库还没有已登记 Release，且平台内构建能力未就绪。

## 不做的事

- 不伪造平台构建执行器。
- 不假设 GitHub/GitLab 私有仓库读取凭据结构。
- 不假设镜像仓库推送凭据结构。
- 不允许未登记镜像 digest 的项目进入节点部署。

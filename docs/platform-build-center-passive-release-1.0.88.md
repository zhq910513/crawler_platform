# 平台构建中心与被动爬虫项目协作 v1.0.88

## 结论

`crawler_platform` 是发布、调度和运行事实源。`crawler_platform_spiders` 是长期稳定的被动运行外壳与业务插件分发包。

爬虫项目不主动 CI/CD，不保存平台 Token，不主动调用平台注册 Release。

## 当前实现边界

v1.0.88 没有伪造完整构建中心。当前仍 fail-closed，因为真实代码中还没有：

```text
平台构建执行器
代码仓库读取凭据
镜像仓库推送凭据
```

未登记 Release 时，项目发布流水线会阻断。

## 后续标准链路

```text
crawler_platform 创建 Build Job
  ↓
构建执行器拉取爬虫项目源码
  ↓
调用 bash scripts/platform_build_contract.sh
  ↓
生成 .release/crawler_manifest.json
  ↓
平台构建镜像并推送 registry
  ↓
平台读取 imageDigest 并登记 Project Release
  ↓
Manifest Diff
  ↓
人工确认 Release 激活
  ↓
新 Run 使用新 release/imageDigest
```

## 热更新保护

Run 创建后必须冻结：

```text
releaseId
imageRepository
imageDigest
entryModule
entryFunction
parametersSnapshot
configBindingsSnapshot
credentialBindingsSnapshot
```

Release 激活只影响后续新 Run；已创建、排队、运行中的 Run 都继续使用自身 Snapshot。

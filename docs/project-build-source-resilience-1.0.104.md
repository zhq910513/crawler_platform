# 平台构建中心源码获取韧性 v1.0.104

本版本把源码获取从单一路径改成多级兜底：

1. `git clone`，优先保留 commit 元数据。
2. 本地源码包目录 `CRAWLER_PROJECT_SOURCE_BUNDLE_DIR`，支持 `zip`、`tar.gz`、`tgz`。
3. GitHub 官方 codeload/archive 归档包。
4. 上次成功构建后保存的本地源码缓存 `CRAWLER_PROJECT_SOURCE_CACHE_ROOT`。

推荐源码包命名：

```text
<repo>__<ref>.zip
<repo>-<ref>.zip
<sha256(repo+ref前24位)>.zip
```

例如：

```text
crawler_platform_spiders__main.zip
crawler_platform_spiders-main.tar.gz
```

远程自动部署也增加了运行目录忽略契约：`data/` 等本地运行目录不会再被当成源码改动阻断部署；未知未跟踪文件仍会阻断，避免误覆盖真实手工改动。

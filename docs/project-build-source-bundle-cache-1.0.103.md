# 平台构建中心源码包与源码缓存兜底 v1.0.103

v1.0.103 将源码获取从“只能远程拉取”扩展为多输入兜底：

1. `git clone`。
2. 已上传源码包：`/data/project-builds/source-bundles`。
3. GitHub 官方归档包：`codeload.github.com` / `github.com/archive`。
4. 本地源码缓存：`/data/project-builds/source-cache`。

源码包按 `repositoryUrl + refName` 生成稳定 key，支持 `.zip`、`.tar.gz`、`.tgz`。平台不会内置第三方 GitHub 代理，避免供应链风险；如果控制端无法访问 GitHub，推荐通过平台可访问的镜像仓库地址或源码包上传接口提供源码输入。

同时，远程部署入口会在工作区检查前写入 `.git/info/exclude`，忽略 `data/`、`.release/` 和本地数据库文件，避免 MySQL、Redis、构建缓存、日志等运行期目录阻断自动部署。

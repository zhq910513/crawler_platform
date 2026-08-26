# 平台构建中心源码归档包兜底 v1.0.101

## 背景

控制端服务器在境内网络环境下访问 GitHub 时，`git clone` 可能出现 TLS 断开、低速超时或 443 端口连接失败。v1.0.100 已加入 clone 重试，但如果出口长期不可用，三次重试仍会失败。

## 方案

v1.0.101 在 `git clone` 多次失败后，对标准 GitHub 仓库自动尝试源码归档包兜底：

```text
https://codeload.github.com/<owner>/<repo>/tar.gz/refs/heads/<ref>
https://codeload.github.com/<owner>/<repo>/tar.gz/refs/tags/<ref>
https://github.com/<owner>/<repo>/archive/refs/heads/<ref>.zip
https://github.com/<owner>/<repo>/archive/refs/tags/<ref>.zip
```

成功后，平台把归档包解压到 Build Job 的 `source` 目录，继续执行：

```text
scripts/platform_build_contract.sh
Docker build
Docker push
image digest inspect
Release 登记
```

## 安全边界

- 仅对 `github.com/<owner>/<repo>` 或 `git@github.com:<owner>/<repo>` 标准地址启用自动归档包兜底。
- 解压 tar/zip 前检查路径，禁止绝对路径和 `..` 逃逸。
- 不内置第三方 GitHub 代理，避免供应链污染。
- 私有仓库仍需要控制端预先具备访问权限；归档包兜底主要面向公开 GitHub 仓库和网络/TLS 瞬断。

## Build Job 日志

新增阶段：

```text
SOURCE_ARCHIVE
SOURCE_ARCHIVE_SKIP
```

如果归档包成功，日志会包含归档 URL、根目录和提取到的提交标识。

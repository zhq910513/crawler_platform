# 项目构建源码拉取重试 v1.0.100

## 背景

线上项目发布构建任务在 CLONE 阶段失败，日志显示：

```text
fatal: unable to access ... GnuTLS recv error (-110): The TLS connection was non-properly terminated.
```

这是典型的 GitHub HTTPS/TLS 或出口网络瞬断问题，不应直接让构建任务一次失败。

## 实现

构建中心新增 `_git_clone_source`，替代单次 `git clone`。默认行为：

```text
CRAWLER_PROJECT_GIT_CLONE_ATTEMPTS=3
CRAWLER_PROJECT_GIT_CLONE_RETRY_SECONDS=5
CRAWLER_PROJECT_GIT_CLONE_TIMEOUT_SECONDS=300
```

每次 clone 使用：

```text
git -c http.version=HTTP/1.1 \
    -c http.lowSpeedLimit=1024 \
    -c http.lowSpeedTime=60 \
    -c http.postBuffer=524288000 \
    clone --depth 1 --single-branch --branch <ref> <repo> <target>
```

并设置：

```text
GIT_TERMINAL_PROMPT=0
GIT_HTTP_LOW_SPEED_LIMIT=1024
GIT_HTTP_LOW_SPEED_TIME=60
```

## 结果

- GitHub TLS 瞬断会自动重试。
- 发布页构建任务诊断会显示每次 CLONE 尝试。
- 多次失败后返回明确错误：`源码拉取失败：Git 网络/TLS 连接异常或仓库不可访问`。

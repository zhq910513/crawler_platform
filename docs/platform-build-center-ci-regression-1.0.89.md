# 平台构建中心 CI 回归修复 v1.0.89

## 问题

v1.0.88 的代码契约已经切换为平台构建中心被动 Release 链路，但仓库中可能仍残留 v1.0.87 的测试文件：

```text
backend/tests/test_project_publish_external_release_gate_1087.py
```

该旧测试继续断言：

```text
mode = EXTERNAL_RELEASE_REQUIRED
getSpiderProjectCicdOneClickGuide 出现在 ProjectPublishPage.vue
```

这与当前设计冲突。当前正确契约是：

```text
mode = PLATFORM_BUILD_CENTER_REQUIRED
blockedReasonCode = PLATFORM_BUILD_CENTER_NOT_READY
supportedReleasePath = PLATFORM_MANAGED_BUILD_RELEASE_REGISTRATION
```

## 修复

v1.0.89 保留同名测试文件作为覆盖式修复，避免使用 ZIP 覆盖仓库时旧测试文件残留。新测试断言当前平台构建中心契约，不再要求外部 CI 主动注册入口。

## 边界

本版本没有实现完整构建中心，也没有恢复爬虫项目主动 CI/CD。平台仍 fail-closed，直到平台构建执行器、代码仓库读取凭据、镜像仓库推送凭据等真实能力完成。

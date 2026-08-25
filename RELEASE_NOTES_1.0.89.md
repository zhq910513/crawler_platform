# v1.0.89 发布说明

## 背景

v1.0.88 已将项目发布链路从“爬虫项目主动外部 CI 注册 Release”纠正为“平台构建中心被动构建/注册 Release”。CI 失败原因是旧版 `test_project_publish_external_release_gate_1087.py` 仍断言 `EXTERNAL_RELEASE_REQUIRED` 和发布页外部 CI 指引。

## 变更

- 新增兼容同名测试 `backend/tests/test_project_publish_external_release_gate_1087.py`，将旧测试文件名的断言同步到当前平台构建中心契约。
- 版本统一提升到 `1.0.89`。
- 保持项目发布 fail-closed：构建中心未就绪时继续返回 `PLATFORM_BUILD_CENTER_REQUIRED` / `PLATFORM_BUILD_CENTER_NOT_READY`。
- 不恢复爬虫项目主动 CI/CD，不恢复发布页外部 CI 主动注册指引。

## 验证

- Python 编译检查通过。
- Shell `bash -n` 检查通过。
- 项目发布构建中心门禁与旧测试文件名兼容测试通过。
- 版本一致性检查通过。
- ZIP 解压后与源码 sha256 manifest 一致。

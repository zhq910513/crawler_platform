# v1.0.96 平台构建中心可观测性

v1.0.96 解决的是项目发布进入真实构建后“失败不可诊断”的问题。

## readiness 诊断

构建中心自检数据新增 `diagnostics`：

- `buildEnabled`
- `gitAvailable`
- `dockerCliAvailable`
- `dockerDaemonViaCli`
- `dockerSocketPath`
- `dockerSocketExists`
- `dockerEngineApiAvailable`
- `dockerExecutorAvailable`
- `selectedExecutor`
- `imageRepositoryPrefix`
- `buildRoot`
- `buildRootParentExists`

这些字段只用于诊断，不改变平台发布事实模型。

## 构建失败响应

当平台构建中心执行失败时，接口不会只返回单句错误，而是返回：

- `pipelineStatus=BLOCKED`
- `steps[].key=build` 的错误状态
- `buildJob.buildStatus=FAILED`
- `buildJob.currentStage`
- `buildJob.errorMessage`
- `buildJob.buildLogs`

前端项目发布页会展示最近构建日志，方便判断是 git clone、被动构建契约、docker build、docker push、digest inspect 还是 manifest 校验失败。

## 不变规则

构建失败不会登记 Release，也不会继续部署节点。旧 Run 和旧 Release 不受影响。

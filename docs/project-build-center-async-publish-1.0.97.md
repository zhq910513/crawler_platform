# v1.0.97 项目发布异步构建说明

## 问题

前端 Axios 默认超时为 30000ms。项目发布在未登记 Release 时需要真实构建镜像，耗时通常超过 30 秒；如果同步执行，浏览器会先报 `timeout of 30000ms exceeded`。

## 处理方案

发布接口改为两段式：

1. 前端点击发布，后端完成前置检查。
2. 如果仓库未登记 Release，后端创建 `crawler_project_build_job`，返回 `pipelineStatus=BUILDING`。
3. 后端后台线程继续执行构建。
4. 前端轮询 `/project-builds/{buildJobId}` 展示阶段和日志。
5. 构建 `SUCCEEDED` 后，后台完成 Release 登记。
6. 前端自动再次调用发布流水线，继续导入项目、部署 Release、下发节点自检。

## 返回约定

构建中返回：

```json
{
  "pipelineStatus": "BUILDING",
  "canContinue": false,
  "buildJob": {
    "buildStatus": "PENDING",
    "currentStage": "QUEUED"
  }
}
```

构建失败时通过构建任务详情查看：

```json
{
  "buildStatus": "FAILED",
  "currentStage": "DOCKER_BUILD_API",
  "errorMessage": "...",
  "buildLogs": []
}
```

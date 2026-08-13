# 爬虫项目 CI/CD 多执行节点发布规范

## 目标

一份爬虫项目代码可能部署到同一公司的多个执行节点，但构建动作只做一次。标准链路是：Git CI 构建一次镜像、推送一次镜像仓库、注册一次 release；部署目标只在控制台选择，多个执行节点按 `imageRepository@imageDigest` 拉取同一份镜像。

## 控制端行为

### 项目发现接口

`POST /api/v1/discovered-projects` 只接收公司发现凭证和 `manifest`：

```json
{
  "manifest": {
    "companyCode": "ulike",
    "projectCode": "xhs_note_image",
    "imageRepository": "ghcr.io/zhq910513/xhs_note_image",
    "imageDigest": "sha256:...",
    "releaseVersion": "1.0.0",
    "taskDefinitions": []
  }
}
```

公司归属来自 `manifest.companyCode`，后端会校验发现凭证是否属于该公司。CI 不提交节点编号，也不决定部署到哪个执行节点。

### 项目执行节点范围

项目导入后，在“项目管理”里选择一台或多台目标节点并一键部署。新 release 注册后，已绑定节点会变成待预热状态，执行节点空闲时拉取并校验 digest，成功后变为可接收任务。

### 执行节点运行

执行节点领取任务时，控制端返回不可变 release、镜像 digest、任务入口和参数。任务容器只使用 `imageRepository@imageDigest`，不使用 `latest`，也不在执行节点上拉 Git 或构建镜像。

## 操作员职责

操作员只需要安装一次执行节点，并在控制台配置项目部署目标、任务参数、立即执行或调度。操作员不需要在每个执行节点上 `git pull`，也不需要手工运行 Python 文件。

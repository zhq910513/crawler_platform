# 执行节点接入交互修复记录 v1.0.81

## 背景

目标机执行安装脚本后，脚本显示 Agent 容器已启动，但控制台仍需要手动刷新才能看到首次心跳状态。生成接入命令时，页面还会弹出后端 warnings 提示，且弹窗停留在表单区域，用户需要手动滚动到命令区域。

## 本次处理

- `frontend/src/views/ServersPage.vue`
  - 生成命令后自动定位命令面板。
  - 生成命令后启动 5 秒一次的节点状态轮询。
  - 节点上线后自动更新步骤到“等待节点上线”完成态并提示“节点已上线”。
  - 不再对 `joinResult.warnings` 弹出非阻断 warning。

- `frontend/src/views/ProjectPublishPage.vue`
  - 项目发布页内新增执行节点入口同步处理。
  - 节点上线后自动加入已选节点。
  - 关闭 Drawer 或组件卸载时清理轮询定时器。

- `backend/app/templates/install-agent.sh`
  - 成功启动容器后的提示改为控制台会自动刷新首轮心跳状态。

- `backend/app/services/server_service.py`
  - 生成的安装命令内成功提示文案同步调整。

## 未强行处理的点

本次没有擅自修改 Agent 镜像版本契约。当前项目已支持 Agent 版本独立于平台版本，是否要求 Agent 镜像跟平台 `APP_VERSION` 强绑定，需要结合你的正式升级策略确认，不能仅根据一次目标机输出直接改契约。

不过，从现场命令可见目标机拉取的是 `crawler_platform_agent:1.0.71`，如果这是生产 `.env` 遗留值，仍可能造成旧 Agent 与新平台不兼容。需要在目标机或平台容器中确认：

```bash
docker logs --tail 200 crawler-agent
docker inspect -f '{{.Config.Image}}' crawler-agent
```

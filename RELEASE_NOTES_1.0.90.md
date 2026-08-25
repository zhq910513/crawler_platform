# Release Notes v1.0.90

## 目标

修复项目发布页把“节点地址采集中”的执行节点仍标记为“可部署”的问题。

## 变更

- 项目发布页新增执行节点地址就绪判断。
- 执行节点未上报 serverIp / reportedAddress / hostIp / publicIp / hostname 时，前端不再显示“可部署”。
- 后端项目发布流水线同步将缺少上报地址的在线 Agent 判定为不可部署，避免绕过前端。
- 新增回归测试覆盖“在线但地址未采集”的阻断场景。

## 兼容性

Agent 首次心跳正常上报 hostIp、publicIp 或 hostname 后即可进入可部署状态。

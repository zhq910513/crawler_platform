# crawler_platform 1.0.16 发布说明

## 版本定位

本版本围绕“多公司、多服务器、多爬虫项目”的标准交付流程做平台端增强：新服务器通过 Agent 接入向导进入公司资源池；已有 Agent 的服务器通过项目部署中心承载第 N 个爬虫项目；CI/CD 仍只负责构建一次镜像并注册 release，平台负责把 release 分发到多 Agent。

## 新增能力

- Agent 接入向导后端能力：新增一次性 joinToken、安装命令生成、安装脚本下载和 bootstrap env 换取接口。
- 安装脚本 `deploy/scripts/install-agent.sh` 支持安装前 doctor：平台端口连通、Docker 权限、工作目录、磁盘、端口占用等初检。
- 新增服务器标签、能力、工作目录、registry 凭证引用字段，支持公司资源池和后续能力匹配。
- 新增项目 release 部署接口：可将一个 release 一次部署到同公司多台已安装 Agent 的服务器。
- 新增部署计划与部署目标表，记录 release 到多 Agent 的分发状态。
- Agent 镜像拉取结果会同步更新项目服务器池和部署目标状态。
- 任务定义与任务增加离线兜底策略字段预留：`allowOfflineRun` 与 `offlinePolicy`。
- 前端 Agent 节点页增加“Agent 接入向导”，平台直接生成运维可复制的安装命令。
- 前端项目服务器池增加“部署当前版本”入口，便于已有 Agent 服务器部署第二个、第三个爬虫项目。

## 运维交互

- 新服务器：平台生成命令，运维在服务器执行一次；通过检查后 Agent 自动上线。
- 第二个项目：平台选择公司、项目、release 和目标 Agent，点击部署；服务器不再拉源码、不再重复安装 Agent。
- 多服务器：CI/CD 不逐台部署；平台记录每台 Agent 的 READY / OUTDATED / WARMING / FAILED。

## 验证

- 后端新增 Agent joinToken / bootstrap / install 脚本契约测试。
- 后端新增 release 多 Agent 部署契约测试。
- Alembic head 升级为 `0006_agent_deploy`。

# crawler_platform 1.0.84

## 变更摘要

- Agent 安装脚本自动采集宿主机主机名与默认网卡地址，并写入 `/opt/crawler-agent/.env`。
- Join Token 换取配置时，控制端保存安装脚本采集到的节点地址到 `crawler_server.server_ip`，同时保存在 `metrics.hostname / hostIp / publicIp / reportedAddress`。
- 复用长期 Agent 凭据时，安装脚本也会把本次采集到的主机标识提交给 `/api/v1/agent-bootstrap/resume-env`，避免旧凭据复用后节点地址仍为空。
- Agent 心跳新增 `hostname / hostIp / publicIp` 上报字段；控制端收到心跳后自动补齐节点地址。
- 项目发布页修正部署节点判断：未完成首次心跳的节点不再显示“可部署”，改为显示“等待首次心跳 / 待接入 / 离线”等真实阻断原因。
- 执行节点列表与项目发布页统一使用 `serverIp -> metrics.reportedAddress -> metrics.hostIp -> metrics.publicIp -> metrics.hostname` 展示节点地址。

## 测试

- Python 编译检查通过。
- Shell `bash -n` 检查通过。
- 关键测试通过：`84 passed`。
- 版本一致性检查通过：`releaseVersion=1.0.84`，`warnings=0`。
- ZIP 解压 manifest 校验通过。

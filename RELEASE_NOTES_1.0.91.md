# Release Notes 1.0.91

## 背景

v1.0.90 把“节点地址采集中”纳入项目发布部署节点门禁后，现场发现部分旧 Agent 已经稳定在线并上报资源指标，但由于旧 Agent 镜像没有上报 `hostIp/publicIp/hostname`，项目发布页仍会显示“节点地址采集中”，导致在线节点无法进入后续发布链路。

## 修复

- Agent 心跳接口增加控制端观测远端地址兜底：优先读取 `X-Forwarded-For`，其次读取 `X-Real-IP`，最后读取 TCP client host。
- 只接受合法 IPv4 / IPv6 地址，避免把 `testclient`、非法 header 或其他伪字符串写入节点地址。
- 当旧 Agent 未上报主机身份字段时，控制端使用观测到的远端 IP 回填：
  - `server.server_ip`
  - `metrics.observedRemoteAddress`
  - `metrics.reportedAddress`
- 项目发布页与执行节点页把 `observedRemoteAddress` 纳入地址展示和部署可用性判断。
- 保留 v1.0.90 的安全门禁：如果既没有 Agent 上报地址，也没有合法观测远端 IP，节点仍显示“节点地址采集中”，不可部署。

## 测试

- `python -m compileall -q backend/app agent/crawler_agent runtime/crawler_runtime backend/tests deploy/scripts/check-alembic-graph.py`
- `bash -n backend/app/templates/install-agent.sh deploy/scripts/commercial-release-gate.sh deploy/scripts/deploy-single-server.sh`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_agent_observed_remote_address_1091.py tests/test_project_publish_server_address_gate_1090.py tests/test_agent_host_identity_1084.py`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_project_publish_platform_build_gate_1088.py tests/test_project_publish_external_release_gate_1087.py tests/test_runtime_resource_resolution_1086.py`
- `bash deploy/scripts/check-version-consistency.sh`

## 注意

该版本没有修改爬虫项目，也没有实现平台构建中心；只修复执行节点地址识别与项目发布节点门禁之间的联动问题。

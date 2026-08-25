# Release Notes v1.0.85

## 类型

执行节点心跳异常展示修复 / Agent 稳定性修复

## 背景

v1.0.84 已完成执行节点地址自动采集和部署可用判断修复。现场验证中，节点已经上线并持续上报资源指标，但执行节点列表仍展示历史网络异常：

```text
Agent 主循环异常：HTTPConnectionPool(... /api/v1/agent-heartbeats ... Connection refused)
```

该异常表示 Agent 某一次访问控制端时控制端端口短暂不可达。后续心跳已经成功时，该历史瞬时异常不应继续作为“最近异常”展示。

## 修复

- Agent 主循环将控制端临时不可达的 `PlatformUnavailable` 单独处理。
- `HTTPConnectionPool`、`Connection refused`、`Max retries exceeded` 等控制端瞬时网络异常不再写入 Agent `lastError`。
- 控制端收到成功心跳后，会清洗旧 Agent 上报的历史瞬时控制端网络异常。
- 执行节点页对在线节点隐藏已恢复的瞬时控制端连接异常，避免误判为当前节点故障。
- 最近异常列增加 tooltip，避免长异常直接撑开表格。

## 测试

- Python 编译检查通过。
- Shell bash -n 检查通过。
- 核心回归测试通过：91 passed。
- 版本一致性检查通过：releaseVersion=1.0.85 warnings=0。
- ZIP 解压 manifest 校验通过。

## 注意事项

如果节点继续频繁出现 `Connection refused`，应检查控制端服务、反向代理、宿主机防火墙和部署期间服务重启窗口。v1.0.85 只清理已经恢复的瞬时错误，不隐藏真实的 Docker、鉴权、任务执行和 Agent 指令异常。

# Agent 本地 Spool 设计

每个 TaskRun 在 Agent 本地有独立目录：

```text
/var/lib/crawler-agent/runs/<run_id>/
├── task.json
├── resources.json
├── secrets.json
├── execution.json
├── agent-state.json
├── stdout.ndjson
├── stderr.ndjson
├── events.ndjson
├── upload.state.json
├── result.json
├── errors.ndjson
├── last_error.json
└── finish.json
```

日志采集顺序：

```text
容器 stdout/stderr
→ 写入本地文件
→ 分配 stream + seq
→ 上传平台
→ 平台 ACK
→ 更新 upload.state.json
```

平台断线时：

- 容器继续运行。
- 日志继续写本地。
- ERROR 继续写 events.ndjson。
- finish.json 继续保存。
- 网络恢复后按 offset 和 seq 补传。

Agent 重启时：

- 扫描运行目录。
- 找回还在运行的容器。
- 根据本地 seq 跳过已采集日志。
- 已完成但未上传的运行只补传，不重新执行。


# Platform ↔ Agent V2 协议摘要

统一前缀：

```text
/api/agent/v2
```

主要接口：

```text
POST /register
POST /heartbeat
POST /claim
POST /runs/{run_id}/starting
POST /runs/{run_id}/started
POST /runs/{run_id}/heartbeat
GET  /runs/{run_id}/control
POST /runs/{run_id}/logs
POST /runs/{run_id}/events
POST /runs/{run_id}/container-events
POST /runs/{run_id}/finish
```

任务认领后，平台返回 `lease_token`。之后运行级接口必须携带：

```text
X-Run-Lease-Token: <lease_token>
```

平台校验：

```text
agent_id
server_id
run_id
lease_token
```

Agent 只接收固定执行合同：

```json
{
  "protocol_version": "2.0",
  "run_id": 1001,
  "lease_token": "...",
  "image": {
    "ref": "crawler_platform_spiders@sha256:...",
    "profile": "api"
  },
  "files": {
    "task": {},
    "resources": {},
    "secrets": {}
  },
  "runtime": {
    "cpu_limit": 2,
    "memory_limit_mb": 4096,
    "timeout_seconds": 3600
  }
}
```

平台不向 Agent 下发任意 Python 模块、函数、Shell 命令或宿主机 Volume。

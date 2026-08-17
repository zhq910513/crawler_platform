# crawler_platform 1.0.69

## 运行总览事实检测角色纠偏

- 运行总览从“预设超管待办清单”改为“真实运行事实 + 自动证据判定”。
- 新增 `PENDING` 检查语义：当前没有足够证据时标记为“待场景验证”，不再等价为 `WARN`，也不计入运行异常；API 同步归属 `AUTO_VERIFY`，不携带人工处理角色、修复按钮或手动命令。
- `WARN` 只用于已有实时证据确认的非阻断运行问题，例如已接入且启用的执行节点离线/心跳超时、在线执行节点 Docker 异常、实际运行镜像 digest 与当前发布 digest 不一致。
- 控制端公网回环 `/health` 探测失败时，如果存在新鲜 Agent 心跳，使用执行节点实时心跳作为更强证据，现有节点通信判定为已验证。
- Registry 控制端探测失败时，如果在线执行节点正在运行目标镜像并上报实际 digest，现有节点镜像分发链路判定为已验证；未来新节点仍在目标节点接入预检中独立验证。
- 内网/VPN 控制端地址不再天然产生“需确认”告警；已有在线 Agent 时按现有节点运行事实通过，无在线节点时等待新节点接入场景验证。
- Registry 认证/TLS、安全组来源限制等安全治理项从运行检查项拆出为 `securityAdvisories` / 安全建议，不参与 `warningCount`、总体运行状态和 `readyForRemoteAgent`。
- 运行总览仅把 `FAIL/WARN` 作为“当前异常”；`PENDING` 单独显示“待场景验证”，并明确由新节点接入、后续心跳或实际镜像拉取自动补证据。
- 新增运行上下文提醒：只有真实存在 `WAITING_RESOURCE` 运行实例时才提示任务等待资源；单纯“执行节点=0”不会制造告警。
- 平台自检快照继续兼容旧表结构，通过 `result_json` 持久化 `pendingCount`、`verifiedCount`、`securityAdvisoryCount`，无需新增数据库迁移。
- 执行节点页、项目发布页同步更新状态语义，不再传播“需确认/请超管确认”的旧角色。

## 验证

- 后端 `python -m compileall` 通过。
- `backend/tests/test_rebuild_contract.py`：55 passed。
- 其余后端测试文件：30 passed。
- 新增契约测试覆盖“未知外部条件 => PENDING 而非 WARN”“在线 Agent 运行证据覆盖控制端公网回环探测失败”“已接入且启用节点明确离线 => 真实运行 WARN”。
- 前端依赖安装在当前交付容器中无法完成，因此未宣称 `npm run build` 已通过；已使用全局 TypeScript 对 16 个 Vue `script setup` 与 `api.ts` 执行静态语法转译检查，并通过现有前端文案/契约门禁，保留完整 Vue 构建验证边界。

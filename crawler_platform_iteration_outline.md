# crawler_platform 产品与架构迭代大纲

> 状态：三轮架构推敲后的规划基线  
> 日期：2026-08-18  
> 当前仓库核验版本：`1.0.76`  
> 项目定位：控制面 / 治理面 / 发布面 / AI 工程控制面  
> 规划主线：`v1 基建 → v2 单文件 AI 迁移 → v3 复杂项目理解与迁移 → v4 MCP + 爬虫智能 → v5 多 Agent 工程工厂`

---

## 0. 文档目的

`crawler_platform` 不应继续被理解成“管理几个定时 Python 脚本的后台”。

最终产品应成为整个爬虫体系的 **Control Plane**：

```text
公司 / 项目 / Release / Task Definition / Task / Schedule / Run
                         │
                         ├── Agent / 执行节点
                         ├── 账号与资源
                         ├── 镜像与 digest
                         ├── 日志 / Artifact / Evidence
                         ├── AI Migration Job
                         ├── MCP Capability Governance
                         └── Multi-Agent Workflow
```

平台只负责：

1. 管理事实；
2. 管理版本；
3. 管理发布；
4. 管理调度；
5. 管理权限；
6. 管理运行状态；
7. 管理证据；
8. 管理 AI 工程流程；
9. 管理工具能力授权；
10. 管理审批与验收。

平台 **不负责实现具体目标网站业务爬虫**，不 import 业务 Python，不复制 `crawler_platform_spiders` 的 SDK 能力。

---

# 1. 三轮推敲后的核心结论

## 第一轮：职责边界

三层体系必须彻底分离：

```text
crawler_platform
    =
Control Plane

crawler_platform_spiders
    =
Stable Runtime Shell / Crawler SDK Distribution

spiders/<platform>/<task>.py
    =
Hot-Pluggable Task Plugin
```

硬规则：

- 平台数据库是唯一生产调度事实源。
- 平台不读取业务代码决定运行逻辑。
- 外壳不保存生产调度事实。
- 具体爬虫不直接访问平台内部数据库。
- 具体爬虫只通过标准运行上下文、账号、配置、资源、Artifact、Checkpoint 等协议获取能力。
- `sch.py` 不成为生产调度来源。

## 第二轮：协议与热更新

“热更新”统一定义为：

> **Release 级零中断切换，而不是 Python 进程内 reload。**

已有 Run 一旦启动，必须冻结：

```text
releaseId
releaseVersion
imageRepository
imageDigest
definitionKey
entryModule
entryFunction
Task Contract Revision
协议版本
运行参数快照
资源绑定快照
账号绑定策略快照
```

后续发布新 Release：

- 不停止旧 Run；
- 不替换旧 Run 容器；
- 不修改旧 Run 代码；
- 新增 Task 被发现；
- 新 Run 才使用新 Release；
- 已有生产 Task 的调度、参数、账号和资源配置不被代码发现流程覆盖。

## 第三轮：从 v2-v5 倒推 v1

未来 AI 必须在平台已有标准上工作，而不是反过来要求平台迁就 AI。

因此 v1 必须先冻结：

- Manifest Protocol
- Task Contract Protocol
- Run Snapshot / Run Context Protocol
- Runtime Event & Result Protocol
- Capability / Resource Binding Protocol
- Artifact & Evidence Protocol
- Checkpoint Protocol
- Account Status Event Protocol
- 版本兼容策略
- Release Diff
- Acceptance Gate

否则 v2-v5 会变成“LLM 猜项目结构”。

---

# 2. 当前已核验基础

当前平台已经具备正确的核心方向：

- 平台数据库是唯一调度事实来源。
- `sch.py` 仅作为任务目录/定义的辅助来源，正式任务由平台创建。
- 项目具有任务定义、正式任务、运行实例等分层。
- 支持多执行节点范围。
- Scheduler 先生成 Run，再动态分配 Agent。
- Agent 使用精确镜像 digest。
- 每个运行实例使用独立容器。
- 已有 Run 保存 release / image digest 快照。
- 发布新镜像不打断正在运行的任务。
- 平台版本、Agent 版本、Agent 通信协议版本已经解耦。

后续不推翻这些设计，而是继续补齐“可规模化扩展与 AI 化所需的协议层”。

---

# 3. 产品领域模型冻结方向

建议 v1 最终把以下领域模型明确下来：

```text
Company
  └── Project
        ├── Project Release
        │      └── Manifest
        │             └── Task Definition Revision
        │
        ├── Task Definition
        │      └── Production Task
        │             ├── Schedule
        │             ├── Parameter Binding
        │             ├── Credential Binding
        │             └── Resource Binding
        │
        └── Run
               ├── Run Snapshot
               ├── Agent Lease
               ├── Runtime Events
               ├── Logs
               ├── Artifacts
               ├── Data Quality Result
               └── Checkpoint
```

## 3.1 必须区分的对象

### Task Definition

来自代码世界。

描述：

- 这个任务叫什么；
- 从哪里执行；
- 需要哪些配置；
- 需要哪些账号；
- 需要哪些资源；
- 输出什么；
- 支持什么能力。

### Production Task

来自生产配置世界。

描述：

- 是否启用；
- 参数是什么；
- 用哪些账号；
- 用哪个数据库；
- 调度是什么；
- 运行在哪些节点；
- 并发策略是什么。

原则：

> `Task Definition != Production Task`

代码更新不能覆盖 Production Task。

### Project Release

一次不可变发布物：

```text
releaseVersion
imageRepository
imageDigest
manifest
protocol versions
build metadata
```

### Run

不可变执行快照。

历史 Run 必须可以回答：

> 这次运行究竟使用了哪一份代码、哪个 digest、什么参数和什么契约？

---

# 4. 三层之间的协议宪法

平台必须把协议视为独立产品，不跟某个 Python 类绑定。

## P1. Project Release Manifest Protocol

方向：

```text
crawler_platform_spiders / CI
          ↓
crawler_platform
```

职责：

- 注册项目 Release；
- 描述镜像；
- 描述 Task Definition 集合；
- 声明协议兼容性；
- 提供任务 diff 的输入。

当前 `manifestVersion` 继续保留。

目标内容：

```text
manifestVersion
projectKey / projectCode
releaseVersion
imageRepository
imageDigest
supportedRuntimeProtocol
taskDefinitions[]
build metadata
```

Manifest 是发布事实，不是生产任务配置。

---

## P2. Crawler Task Contract Protocol

方向：

```text
Business Task
    ↓
Runtime Shell
    ↓
Manifest
    ↓
Platform
```

稳定身份：

```text
projectCode + definitionKey
```

`definitionKey` 必须稳定，不以文件路径、类名、中文名作为唯一身份。

契约负责声明：

```text
definitionKey
taskName
platformCode
entryModule
entryFunction
executionMode
idempotencyPolicy
requiredCapabilities
resourceRequirements
requiredConfigs
requiredCredentials
outputTables
allowOfflineRun
```

未来以兼容方式逐步增加：

```text
inputSchema
outputSchema
checkpointCapability
artifactCapability
dataQualityContract
retrySemantic
rateLimitScope
```

---

## P3. Run Snapshot / Run Context Protocol

方向：

```text
Platform
  ↓
Agent
  ↓
crawler_runtime
  ↓
Business Task
```

平台在 Run 创建时冻结运行事实。

协议逻辑字段至少分为：

```text
identity
release
task
parameters
configuration bindings
credential bindings
resource bindings
execution policy
artifact paths
checkpoint reference
trace context
```

实现传输可以继续使用现有 payload / 环境变量 / JSON 机制。

硬规则：

- 业务代码不得自行“猜” company/project/run。
- 平台不应要求业务代码反向访问控制面数据库补上下文。
- 敏感信息只传执行所需最小范围。

---

## P4. Runtime Event & Result Protocol

方向：

```text
Business Task
   ↓
crawler_runtime
   ↓
Agent
   ↓
Platform
```

统一表达：

```text
TASK_START
CONFIG_LOADED
ACCOUNT_ACQUIRED
REQUEST_*
PARSE_*
SAVE_*
CHECKPOINT_*
TASK_PROGRESS
TASK_SUCCESS
TASK_FAILED
```

结果必须至少表达：

```text
status
message
metrics
error category
failed stage
exit code
```

平台不能仅用“进程退出 0”代表业务数据正确。

---

## P5. Capability / Resource Binding Protocol

平台只负责绑定，不实现爬虫能力。

任务声明：

```text
requiredCapabilities
resourceRequirements
requiredConfigs
requiredCredentials
```

Agent 声明：

```text
Agent capabilities
resource capacity
runtime compatibility
```

调度器做能力匹配。

未来可以支持：

```text
requests
scrapy
browser
playwright
har
ocr
proxy
js-analysis
mcp-tool-access
```

---

## P6. Artifact & Evidence Protocol

Run 不应只留下 stdout。

统一 Artifact 类型：

```text
log
export
sample
screenshot
html_snapshot
har
trace
network_record
diagnostic
generated_code
test_report
diff_report
```

v4 后 Evidence 将成为 AI 分析的核心输入。

---

## P7. Checkpoint Protocol

平台负责：

- 保存 checkpoint 引用；
- 展示 checkpoint；
- 在 retry/resume 时把 checkpoint 交给运行时。

业务负责：

- 定义 checkpoint 内容；
- 正确恢复业务进度；
- 保证 checkpoint 与业务幂等语义一致。

镜像更新不能自动把旧 Run 迁移到新版本。

---

## P8. Account Status Event Protocol

继续坚持已有方向：

```text
company + platformCode + credentialKey
```

业务只上报最后已知状态事件。

平台不高频扫描各公司的 Redis / MySQL / Mongo 来猜 Cookie 是否有效。

---

# 5. 协议版本规则

组件版本和协议版本必须彻底独立。

## 5.1 组件版本

```text
crawler_platform version
crawler_agent version
crawler_platform_spiders shell version
business project releaseVersion
```

分别升级。

## 5.2 协议版本

```text
Agent Protocol Version
Manifest Version
Task Contract Version
Run Context Version
Runtime Event/Result Version
Artifact Protocol Version
Checkpoint Protocol Version
Account Status Protocol Version
```

分别升级。

## 5.3 版本策略

Schema 型协议建议使用“Major 整数版本”：

```text
"1"
"2"
```

规则：

- 新增可选字段：不升 Major；
- 改字段含义：升 Major；
- 删除必填字段：升 Major；
- 修改必填结构：升 Major；
- 组件发布 patch/minor 不自动推动协议版本。

平台在 Release 注册阶段完成兼容性预检。

不兼容 Release 必须在进入生产任务调度前被阻断。

---

# 6. 热插拔任务发布模型

标准链路：

```text
开发人员新增 spiders/<platform>/<task>.py
        ↓
TASK_DEFINITION
        ↓
Contract Validation
        ↓
Unit / Acceptance Test
        ↓
CI Build
        ↓
Immutable Image Digest
        ↓
Generate Manifest
        ↓
Register Release
        ↓
Platform Manifest Diff
        ↓
ADDED / UPDATED / UNCHANGED / REMOVED
        ↓
Release Ready
        ↓
新 Run 使用新 Release
```

## 6.1 ADDED

平台：

- 自动登记新的 Task Definition；
- UI 显示“发现新任务”；
- 可以允许操作员基于 Definition 创建正式 Task；
- 不自动生成生产调度。

## 6.2 UPDATED

平台：

- 保留稳定 `definitionKey`；
- 记录新的 Definition Revision / fingerprint；
- 对比 Contract 是否兼容；
- 不覆盖已有 Production Task 参数、调度、账号和资源绑定。

非破坏性更新可以随 Release 激活进入新 Run。

破坏性 Contract 变化必须要求人工确认或迁移。

## 6.3 REMOVED

不能自动删除生产 Task。

应：

- 标记 active Release 中实现缺失/废弃；
- 阻止错误的新 Run；
- 保留历史 Run；
- 提示操作员处理已有调度；
- 不修改历史 Release。

---

# 7. Release 激活与节点预热

建议将 Release 状态产品化：

```text
DISCOVERED
VALIDATING
READY
ACTIVE
BLOCKED
SUPERSEDED
```

节点镜像状态：

```text
OUTDATED
WARMING
READY
FAILED
```

发布新 Release 时：

- 正在运行旧 digest 的容器不停止；
- Agent 空闲后预热；
- 新 Run 启动前必须按 Run Snapshot 校验 digest；
- 只有兼容且 READY 的 Release 才允许进入新的生产运行。

---

# 8. v1.0：基础设施冻结阶段

目标：

> 让平台成为一个“任何未来 AI 都可以安全接入”的稳定控制面。

## 8.1 必做

### 协议

- Manifest Protocol v1 定稿。
- Task Contract v1 定稿。
- Run Context v1 定稿。
- Runtime Event/Result v1 定稿。
- Artifact v1 定稿。
- Checkpoint v1 定稿。
- Account Status 协议正式纳入协议矩阵。
- 协议兼容检查。

### Release

- Manifest Diff。
- Task Definition Revision。
- task fingerprint。
- 新增/修改/删除任务差异展示。
- Release compatibility status。
- Release 激活门禁。
- Agent 镜像预热与 readiness 展示。

### Task

- Task Definition 与 Production Task 彻底区分。
- Definition 更新不覆盖生产配置。
- Task Contract diff。
- 参数 Schema 预留。
- Resource / Credential Binding 标准化。

### Run

- Immutable Run Snapshot。
- Run 生命周期统一。
- 失败阶段分类。
- Artifact Index。
- Checkpoint Metadata。
- 数据质量状态与程序执行状态分离。

### Observability

- Runtime event sequence。
- 实时日志。
- stage filtering。
- Agent snapshot。
- release/digest/task fingerprint 一键查看。

### 自动化

- 新 Release 自动解析。
- Manifest 自动 diff。
- 协议自动校验。
- 镜像自动预热。
- Release readiness 自动判断。
- 不把可由脚本/CI/平台完成的动作默认交给人工。

---

# 9. v2.0：单文件 AI 迁移工厂

目标：

> 用户上传一个已经可以运行并入库的单文件爬虫，系统将其转成符合 `crawler_platform_spiders` 标准的 Task Plugin Candidate。

流程：

```text
Upload
 ↓
Static Analysis
 ↓
Dependency Inventory
 ↓
Contract Extraction
 ↓
Missing Dependency Gate
 ↓
Target Scaffold
 ↓
AI Migration
 ↓
Sandbox
 ↓
Static / Contract Test
 ↓
Differential Test
 ↓
Candidate Task
 ↓
Human Review
 ↓
Commit / Release
```

## 硬规则

- 缺 `base.py`、数据库基类、OSS、Redis、配置等真实依赖时必须阻断或要求补充。
- AI 不得虚构字段、session、db、client、config。
- 默认只能修改业务 Task Candidate 和测试。
- AI 不得直接修改稳定 Shell。
- 如果发现公共能力缺口，生成独立“Shell Capability Proposal”。

## 平台新增产品域

```text
AI Migration Job
Migration Source
Dependency Report
Contract Draft
Patch Candidate
Sandbox Run
Test Report
Human Decision
```

---

# 10. v3.0：复杂项目理解与迁移

目标：

支持：

- 多文件；
- 多爬虫；
- 多调度；
- 多资源；
- 多账号；
- Scrapy；
- 混合 requests/browser；
- 旧项目自定义基类。

核心增加：

```text
Project Graph
```

描述：

```text
files
imports
inheritance
entrypoints
schedules
resources
credentials
database outputs
shared modules
```

迁移策略：

> 优先 Adapter，不强制重写成熟框架。

Scrapy：

```text
Scrapy Project
     ↓
Scrapy Adapter
     ↓
Crawler Runtime Protocol
```

平台仍然只认识统一 Task/Run 生命周期。

---

# 11. v4.0：Crawler Intelligence + MCP

目标：

> 平台开始治理“分析目标网站和修复爬虫”的能力。

MCP 定位：

```text
MCP = Capability Bus
```

不是调度器，也不是 Agent 大脑。

平台新增：

```text
Capability Registry
MCP Server Registry
Tool Permission
Tool Invocation Audit
Evidence Workspace
Analysis Job
Repair Candidate
```

典型 Tool：

```text
browser.open
browser.screenshot
browser.network
browser.har
browser.trace
http.request
http.replay
dom.inspect
dom.diff
selector.test
js.search
db.schema.read
artifact.read
crawler.run_test
```

安全原则：

- Tool allowlist；
- company/project/run scope；
- 凭据最小授权；
- 禁止把 Docker Socket/生产 Shell 默认暴露给 LLM；
- Challenge/CAPTCHA/2FA 明确人工或合规服务边界。

---

# 12. v5.0：Multi-Agent Crawler Engineering Factory

目标：

```text
简单需求
  ↓
标准生产候选爬虫项目
```

工作流：

```text
Requirement Agent
        ↓
RequirementSpec
        ↓
Recon Agent
        ↓
EvidenceBundle
        ↓
Architecture Agent
        ↓
CrawlerContract
        ↓
Developer Agent
        ↓
CodePatch
        ↓
Test Executor
        ↓
TestReport
        ↓
QA Agent
        ↓
Review Agent
        ↓
Human Gate
        ↓
Release Candidate
```

不是自由群聊。

每个节点必须有：

```text
input schema
output schema
tool allowlist
token/cost budget
timeout
retry rule
stop condition
acceptance gate
```

---

# 13. 成熟项目吸收矩阵

| 成熟项目 | 吸收优点 | 不照搬部分 | 进入版本 |
|---|---|---|---|
| Crawlab | Spider/Task/Node/Run 产品认知 | 文件同步式分发 | v1 |
| Airbyte | Contract / discover / check / state / acceptance | ETL Source/Destination 模型 | v1-v2 |
| Apify | Release/Actor/Task/Input/Output/Artifact | Marketplace/托管云模型 | v1-v4 |
| Prefect | Capability/Work Pool 思想、并发治理 | 第二套调度器 | v1-v3 |
| Dagster | Data Quality / Asset Check / lineage | Asset-first 全量改造 | v1-v3 |
| Scrapy | 生命周期、Adapter、成熟爬虫组件 | 强制所有项目 Scrapy 化 | v3 |
| Crawlee | HTTP↔Browser Adaptive Transport | 整体 Runtime 替换 | v4 |
| Playwright | HAR/Trace/Context/Network Evidence | 浏览器默认主路径 | v4 |
| Stagehand | deterministic + AI repair | 每次运行调用 LLM | v4-v5 |
| OpenHands | Sandbox / coding agent evaluation | 通用 Agent 直接改生产 | v2-v5 |
| Temporal | durable workflow/event history | v1 直接引入复杂基础设施 | v2-v5 |
| MCP | Tool/Resource 标准总线 | 把 MCP 当 Agent/调度器 | v4-v5 |
| LangGraph / MS Agent Framework | 可恢复确定性 Agent Workflow | 多 Agent 自由群聊 | v5 |

---

# 14. v1 退出标准

只有满足以下条件，才建议进入 v2：

- [ ] 所有正式 Run 都能追溯到 immutable image digest。
- [ ] 新 Release 不会打断旧 Run。
- [ ] 平台可以显示 Manifest Diff。
- [ ] 新增 Task 能被自动发现。
- [ ] Definition 更新不会覆盖 Production Task 配置。
- [ ] 所有协议有明确版本。
- [ ] 不兼容协议在调度前被阻断。
- [ ] Run Context 不依赖业务代码反查平台补齐。
- [ ] TaskResult、错误分类和 Event 能稳定进入平台。
- [ ] Artifact 有统一索引。
- [ ] Checkpoint 有统一引用语义。
- [ ] 账号状态事件协议稳定。
- [ ] 数据质量状态与任务进程状态分离。
- [ ] Release / Agent / Shell / Protocol 版本关系可观测。
- [ ] Fresh Install、升级、回滚、发布门禁全部自动化验证。

---

# 15. 最终产品原则

1. **生产事实唯一。**
2. **运行实例不可变。**
3. **代码定义与生产配置分离。**
4. **新任务热发现，旧任务零中断。**
5. **协议先于 AI。**
6. **确定性规则优先于 LLM。**
7. **AI 默认只修改业务候选代码，不修改稳定 Shell。**
8. **MCP 是工具总线，不是大脑。**
9. **多 Agent 是 Workflow，不是群聊。**
10. **所有 AI 结论必须落到 Evidence、Patch、Test、Decision。**

# crawler_platform 1.0.57 商业化发布检查清单

本清单用于把“测试服跑通”升级为“可商业交付”。正式发布必须给出 `PASS`、`PASS_WITH_RISK` 或 `FAIL` 结论。

## 1. 自动门禁

发布前执行商业发布门禁脚本。正式发布必须使用严格模式，不能跳过前端构建。

- `git diff --check`：检查空白和换行问题。
- Python 编译：覆盖 backend、agent、runtime、migrations、tests；必须通过 Docker Python 工具容器执行，不允许用客户宿主机旧 Python 作为发布判断。
- Shell `bash -n`：覆盖 deploy、agent 安装脚本和 smoke 脚本。
- 后端契约/回归测试：覆盖账号安全、调度、Agent、日志 V2、高频审计过滤。
- MySQL 标识符长度检查：所有表、索引、外键名必须不超过 64 字符。
- 商业契约扫描：禁止 `SELECT *`、组件内直接网络请求、动词路径、硬编码敏感值。
- 宿主机兼容扫描：禁止新增部署脚本对宿主机 Python/npm/jq 的硬依赖。
- 前端构建：通过 Node Docker 工具容器执行 `npm ci && npm run build`，不依赖宿主机 npm/node_modules。

门禁脚本：`deploy/scripts/commercial-release-gate.sh`。单独编译检查可执行：`deploy/scripts/container-compile-check.sh`。

## 2. Fresh Install 验收

- 安装前运行 `deploy/scripts/doctor.sh`，必须能识别 Docker、Compose、权限、端口、磁盘、inode、SELinux、时间同步和镜像源问题；只有 Docker/Compose/权限等最低部署条件不满足时才阻断，Python/npm/curl/git 等缺失只记录 WARNING。
- 使用空数据库初始化，必须保留 admin 登录能力，不能写入测试业务数据。
- 安装完成后输出访问地址、默认账号提示和修改默认密码建议。
- 重复执行安装脚本不得破坏已有数据或产生混乱容器。

## 3. 账号安全验收

- 用户可通过右上角修改密码。
- 管理员可在用户管理页面重置密码。
- 旧密码错误不能修改。
- 弱密码不能修改。
- 修改/重置密码后旧 token 失效。
- 首次登录或重置后 `passwordChangeRequired=true`，前端强制改密。
- 密码明文不得进入 `sys_operation_log` 或运行日志。

## 4. 调度验收

- 手动执行、每日多时间点、每周多日期多时间点、每月多日期多时间点、高级 Cron 均可预览未来 5 次。
- 时间自动去重、排序；非法时间拒绝。
- 业务多时间点支持不同分钟，例如 `07:15`、`09:45`、`12:00`。
- 修改调度不得影响历史运行记录。

## 5. Agent 运维验收

- Agent 心跳上报 CPU、内存、磁盘、inode、load average、runningContainers、availableSlots、Docker 状态、docker.sock 权限、项目目录可写性、lastError。
- 前端执行节点列表展示状态灯、资源卡片、最近心跳、绑定项、Docker 异常和 lastError。
- Agent 离线、Docker 异常、磁盘高水位、资源不足时，任务路由原因必须能解释。

## 6. 日志 V2 验收

- 任务失败可看到生命周期事件、失败阶段、错误类型、是否可重试、错误摘要和建议动作。
- 前端可查看日志尾部、按关键字/日志流过滤并下载完整日志。
- Agent 高频接口不得写入 `sys_operation_log`。
- 日志分段保留末尾换行，不得因为 Schema 裁剪丢失证据。

## 7. 权限与租户隔离验收

- 普通用户只能访问所属公司数据。
- 超级管理员可跨公司管理。
- 后端 API 必须强校验权限；前端隐藏菜单不作为权限依据。
- 越权访问返回 403，不能返回空泛成功。

## 8. 发布结论规则

- `PASS`：所有自动门禁、Fresh Install、smoke-test、升级/回滚演练和权限测试全部通过。
- `PASS_WITH_RISK`：存在明确、可接受、已记录的风险，只允许灰度，不允许全量。
- `FAIL`：任一 P0/P1 门禁失败，禁止发布。

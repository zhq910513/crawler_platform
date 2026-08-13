# crawler_platform 1.0.9 发布说明

## 版本定位

本版本用于任务调度面板简化整改，发布版本固定为 `1.0.9`。

源码包中的历史版本文件仍停留在 `1.0.2`，但代码已经包含 1.0.7 的禁用节点过滤修复和 1.0.8 的管理员自重置密码修复。本次已统一运行版本、镜像默认标签、前端包版本和 Agent 默认版本为 `1.0.9`，并保留上述回归修复。

建议提交信息：

```text
优化任务调度面板简化视图v1.0.9
```

## 本次新增

### 1. 任务调度聚合接口

新增：

```http
GET /api/v1/task-schedule-panels
```

接口以任务为主表，聚合公司、项目、调度、负责人、目标服务器和最近一次运行结果，支持分页及以下筛选：

- 公司、项目、任务名称、任务编码
- 入口模块或函数
- 执行节点、任务组、任务平台
- 任务状态、计划状态、最近运行状态
- 负责人

普通用户由后端强制收敛到所属公司及有权限的项目，不能依赖前端隐藏实现隔离。

### 2. 扁平化任务调度工作台

原任务页面改造为统一工作台，主要能力包括：

- 两行筛选区和分页任务表格
- 公司、项目、节点、入口路径、任务编码一屏展示
- Cron/业务调度说明、下次执行时间、最近完成时间
- 任务状态、自动调度开关、最近运行结果
- 新增任务、编辑任务、编辑调度、立即执行、详情、日志入口
- 超级管理员跨公司筛选；普通用户固定所属公司
- 日志入口可携带 `taskId`、`runId` 跳转执行记录并自动打开详情

### 3. 任务负责人

`crawler_task` 新增可空字段：

```text
owner_user_id BIGINT NULL
```

负责人必须是同公司且启用的用户。老任务保持 `NULL`，前端显示 `-`。

### 4. 数据库索引

新增迁移：

```text
backend/migrations/versions/0004_task_panel.py
```

迁移内容：

- `crawler_task.owner_user_id`
- `idx_task_owner_user(owner_user_id)`
- `idx_run_task_last(task_id, run_id)`
- 短外键名 `fk_task_owner_user`

迁移包含字段、索引和外键存在性检查，并兼容 SQLite 测试环境。

## 主要文件变化

新增：

- `backend/app/api/task_schedule_panels.py`
- `backend/app/services/task_schedule_panel_service.py`
- `backend/app/repositories/task_schedule_panel.py`
- `backend/migrations/versions/0004_task_panel.py`
- `backend/tests/test_task_schedule_panel_contract.py`
- `frontend/src/api/taskSchedules.ts`

重点修改：

- `backend/app/models.py`
- `backend/app/schemas.py`
- `backend/app/services/task_service.py`
- `backend/app/api/__init__.py`
- `frontend/src/views/TasksPage.vue`
- `frontend/src/views/RunsPage.vue`
- `frontend/src/types/api.ts`
- 发布版本和 Alembic 门禁相关文件

## 已执行验证

- Python 编译检查：通过
- Alembic 迁移图检查：通过，唯一 head 为 `0004_task_panel`
- 后端契约和回归测试：`37 passed`
- TypeScript 及 Vue SFC 脚本语法扫描：通过
- 基于本地类型桩的前端 TypeScript 静态检查：通过
- Vue 模板标签平衡检查：通过

当前执行环境没有 Docker，且无法解析 npm registry 域名，因此不能在本环境完成 Docker 商业发布门禁和真实 `npm run build`。部署前必须在有 Docker 和网络/依赖缓存的环境执行：

```bash
bash deploy/scripts/commercial-release-gate.sh
```

必须确认最终输出：

```text
RELEASE_GATE=PASS
```

## 上线验证

完成迁移、构建和启动后检查：

```bash
curl -s http://127.0.0.1:8080/version.json
curl -s http://127.0.0.1:8080/health
docker compose images | grep crawler_platform
```

期望：

- Web `/version.json` 版本为 `1.0.9`
- API `/health` 版本为 `1.0.9`
- API/Web 镜像标签为 `1.0.9`
- Alembic head 为 `0004_task_panel`

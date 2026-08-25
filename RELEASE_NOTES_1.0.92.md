# v1.0.92 平台构建中心最小发布闭环

## 版本定位

本版本把项目发布从“构建中心未就绪阻断”推进到“平台可控的最小构建闭环”。平台继续作为发布事实源：拉取源码、执行爬虫项目被动构建契约、构建镜像、读取不可变 digest、登记 Release，再进入节点部署。

## 主要变更

- 新增 `crawler_project_build_job` 构建任务表与 Alembic 迁移 `0017_project_build_center`。
- 新增平台构建中心服务：`backend/app/services/build_center_service.py`。
- 新增构建任务 API：
  - `GET /api/v1/project-builds`
  - `GET /api/v1/project-builds/{buildJobId}`
  - `POST /api/v1/project-builds`
- 项目发布流水线在构建中心启用时可自动完成：源码拉取、被动构建契约、Docker build、Docker push、digest 读取、Manifest 校验、Release 登记、项目接入和节点部署。
- 保持 fail-closed：未启用构建中心或缺少必要宿主能力时，仍阻断未登记 Release 发布。
- 构建凭据边界保持明确：v1.0.92 不新增仓库读取凭据/镜像推送凭据数据库模型，私有仓库和 registry 登录需由宿主环境预配置。

## 新增配置

```env
CRAWLER_PROJECT_BUILD_ENABLED=0
CRAWLER_PROJECT_BUILD_ROOT=/data/project-builds
CRAWLER_PROJECT_BUILD_TIMEOUT_SECONDS=1800
CRAWLER_PROJECT_IMAGE_REPOSITORY_PREFIX=
CRAWLER_PROJECT_BUILD_PLATFORM=linux/amd64
CRAWLER_PROJECT_BUILD_PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
```

## 测试

- Python compileall：通过。
- Alembic 图检查：通过，唯一 head=`0017_project_build_center`。
- 版本一致性检查：`releaseVersion=1.0.92 warnings=0`。
- 核心回归：`81 passed`。
- 新增构建中心测试：覆盖构建中心启用时的发布流水线自动构建、Release 登记、项目接入、部署指令下发，以及构建任务列表/详情查询。

## 限制

- 当前构建执行器是同步本地 Docker 子进程，不是异步分布式构建队列。
- 私有 Git 仓库和镜像仓库认证仍依赖宿主机预配置，不在数据库中管理凭据。
- 默认 `.env.example` 仍关闭构建中心，生产启用前必须确认 Docker socket、git、registry 登录和安全边界。

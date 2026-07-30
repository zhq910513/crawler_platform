# Bootstrap / CI/CD / Agent 工程化设计

## 职责边界

- crawler_platform：公司、项目、用户、Agent、镜像版本、任务入口、真实生产调度、运行状态和日志。
- crawler_agent：服务器级执行基础设施；一台服务器只需要一个 Agent，可承载多个项目任务容器。
- 爬虫项目：业务代码、Dockerfile、RELEASE_MANIFEST、crawler_project.yml、sch.py 本地测试。
- CI/CD：拉取代码并统一执行 `deploy/bootstrap.sh --non-interactive`。
- bootstrap：环境预检、Agent 安装/复用、镜像发布登记、入口辅助导入；不启动真实任务。
- sch.py：只用于本地测试，不作为生产调度来源。

## 生产调度原则

真实生产调度只以前端平台数据库为准。CI/CD、bootstrap、sch.py、crawler_project.yml 都不能覆盖已有任务调度。

辅助导入入口时，平台使用 `project_id + entry_module + entry_function` 判断重复；重复任务跳过，不覆盖、不更新、不改调度。

## 镜像版本选择规则

前端展示全部历史镜像，并展示 `published_at`。后端强制只有同一 `app_name + image_repository` 中发布时间最新的 ACTIVE release 可以被选择。历史镜像只读。回滚必须重新发布旧代码，生成新的最新 release。

## 服务器接入原则

操作员可能不是 root，项目路径可能任意。项目 bootstrap 默认普通用户执行；只有 Agent 安装、Docker 权限修复、系统目录创建等动作需要 root/sudo。预检失败必须汇总告诉操作员缺少哪些条件。

## 新增后端能力

- Project Bootstrap Token：项目级接入令牌，只允许登记 release、上传部署报告、辅助导入入口。
- Bootstrap API：`/api/bootstrap/context`、`/api/bootstrap/preflight`、`/api/bootstrap/spider-release`。
- 部署日志：记录预检、发布、入口导入结果。
- 任务调度变更历史：前端调度修改写入 `crawler_task_change_log`。

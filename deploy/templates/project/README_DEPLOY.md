# 爬虫项目一键接入说明

1. 在平台前端为项目生成 Project Bootstrap Token。
2. 复制 `.env.example` 为 `.env` 并填写平台地址、token、镜像仓库。
3. 配置 CI/CD 后，每次拉取代码统一执行：`./deploy/bootstrap.sh --non-interactive`。
4. 脚本只登记版本和辅助导入新增入口，不会启动真实生产任务，也不会覆盖前端调度。

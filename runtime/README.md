# crawler-runtime

`crawler-runtime` 是平台任务容器内的统一入口。业务镜像必须包含该包，Agent 会以如下方式启动任务：

```bash
python -m crawler_runtime --entrypoint spiders.example:run --kwargs-json '{"foo":"bar"}'
```

平台会注入环境变量：

- `CRAWLER_RUN_ID`
- `CRAWLER_PROJECT_ID`
- `CRAWLER_PROJECT_CODE`
- `CRAWLER_TASK_ID`
- `CRAWLER_TASK_CODE`
- `CRAWLER_TASK_GROUP`
- `CRAWLER_RUNTIME_MODE`
- `CRAWLER_IO_CLASS`
- `CRAWLER_RESOURCE_LOCKS_JSON`
- `CRAWLER_WORK_DIR=/work`
- `CRAWLER_LOG_DIR=/logs`
- `CRAWLER_CACHE_DIR=/cache`
- `CRAWLER_PROFILE_DIR=/profiles`

业务任务建议把临时文件写入 `/work`，缓存写入 `/cache`，日志或导出文件写入 `/logs`，浏览器 Profile 写入 `/profiles`。不要写容器根目录。

# -*- coding: utf-8 -*-
"""测试服 smoke 项目的静态任务声明。

注意：平台 CI/CD 解析只允许静态 TASKS 字面量，不会 import 或执行本文件。
"""

TASKS = [
    {
        "definitionKey": "smoke_success",
        "taskName": "测试服链路验证任务",
        "entryModule": "spiders.smoke_tasks",
        "entryFunction": "run",
        "defaultParams": {"message": "hello-crawler-platform"},
        "suggestedCron": "*/10 * * * *",
        "executionMode": "SINGLE",
        "idempotencyPolicy": "IDEMPOTENT",
        "requiredCapabilities": {"smoke": True},
        "runtimeMode": "SHARED_ENV_ISOLATED",
        "taskGroup": "smoke",
        "taskMaxConcurrency": 2,
        "groupMaxConcurrency": 4,
        "exclusiveMode": False,
        "ioClass": "LOW",
        "shmSizeMb": 64,
        "logLimitMb": 20,
        "resourceLocks": [],
        "resourceRequirements": {"cpu": 0.25, "memoryMb": 256},
    }
]

from __future__ import annotations

from typing import Any

RESOURCE_CATEGORY_LABELS = {
    "RELATIONAL_DB": "关系型数据库",
    "DOCUMENT_DB": "文档数据库",
    "CACHE_DB": "缓存数据库",
    "OBJECT_STORAGE": "对象存储",
}

RESOURCE_ENGINE_LABELS = {
    "MYSQL": "MySQL",
    "POSTGRESQL": "PostgreSQL",
    "SQLSERVER": "SQL Server",
    "MONGODB": "MongoDB",
    "REDIS": "Redis",
    "ALIYUN_OSS": "阿里云 OSS",
    "S3": "S3",
    "MINIO": "MinIO",
}

RESOURCE_ROLE_LABELS = {
    "MAIN_DB": "主业务数据库",
    "RESULT_DB": "采集结果库",
    "SOURCE_DB": "客户源数据库",
    "RAW_STORAGE": "原始数据存储",
    "COOKIE_CACHE": "账号/账号缓存",
    "TASK_STATE_CACHE": "任务状态缓存",
    "MEDIA_STORAGE": "媒体文件存储",
    "TEMP_STORAGE": "临时中转存储",
    "ANALYTICS_DB": "分析统计库",
    "LOG_STORAGE": "日志存储",
    "OTHER": "其他",
}

ENGINE_CATEGORY = {
    "MYSQL": "RELATIONAL_DB",
    "POSTGRESQL": "RELATIONAL_DB",
    "SQLSERVER": "RELATIONAL_DB",
    "MONGODB": "DOCUMENT_DB",
    "REDIS": "CACHE_DB",
    "ALIYUN_OSS": "OBJECT_STORAGE",
    "S3": "OBJECT_STORAGE",
    "MINIO": "OBJECT_STORAGE",
}

ENGINE_ALLOWED_MODES = {
    "MYSQL": {"HOST_PORT"},
    "POSTGRESQL": {"HOST_PORT"},
    "SQLSERVER": {"HOST_PORT"},
    "MONGODB": {"HOST_PORT", "URI"},
    "REDIS": {"HOST_PORT"},
    "ALIYUN_OSS": {"CLOUD_SERVICE"},
    "S3": {"CLOUD_SERVICE"},
    "MINIO": {"HOST_PORT", "CLOUD_SERVICE"},
}

LEGACY_RESOURCE_TYPE_MAP = {
    "MYSQL_MAIN": ("RELATIONAL_DB", "MYSQL", "MAIN_DB", "HOST_PORT", "mysql_main", "主业务数据库"),
    "REDIS_CACHE": ("CACHE_DB", "REDIS", "COOKIE_CACHE", "HOST_PORT", "redis_cache", "账号缓存库"),
    "MONGO_RAW": ("DOCUMENT_DB", "MONGODB", "RAW_STORAGE", "URI", "mongo_raw", "原始数据存储"),
    "OSS_MEDIA": ("OBJECT_STORAGE", "ALIYUN_OSS", "MEDIA_STORAGE", "CLOUD_SERVICE", "oss_media", "媒体存储"),
}

SENSITIVE_KEYS = {
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "access_key_secret",
    "accesskeysecret",
    "access_key",
    "accesskey",
    "uri",
}


def is_sensitive_key(key: str) -> bool:
    normalized = str(key).replace("-", "_").lower()
    return any(part in normalized for part in SENSITIVE_KEYS)


def validate_resource_shape(category: str, engine: str, connection_mode: str) -> list[str]:
    errors: list[str] = []
    expected = ENGINE_CATEGORY.get(engine)
    if not expected:
        errors.append(f"暂不支持的资源类型：{engine}")
    elif expected != category:
        errors.append(f"资源大类与具体类型不匹配：{category} / {engine}")
    allowed_modes = ENGINE_ALLOWED_MODES.get(engine, set())
    if connection_mode not in allowed_modes:
        errors.append(f"{RESOURCE_ENGINE_LABELS.get(engine, engine)} 不支持连接方式 {connection_mode}")
    return errors


def _missing(config: dict[str, Any], keys: list[str]) -> list[str]:
    return [key for key in keys if str(config.get(key) or "").strip() == ""]


def _validate_port(config: dict[str, Any], key: str = "port") -> str | None:
    value = config.get(key)
    if value in (None, ""):
        return None
    try:
        port = int(value)
    except Exception:
        return f"{key} 必须是 1-65535 的端口号"
    if port < 1 or port > 65535:
        return f"{key} 必须是 1-65535 的端口号"
    return None


def validate_resource_config(engine: str, connection_mode: str, config: dict[str, Any]) -> tuple[str, str]:
    config = config or {}
    missing: list[str]
    errors: list[str] = []
    if engine == "MYSQL":
        missing = _missing(config, ["host", "port", "database", "username"])
        errors.extend([_validate_port(config)] if _validate_port(config) else [])
    elif engine == "POSTGRESQL":
        missing = _missing(config, ["host", "port", "database", "username"])
        errors.extend([_validate_port(config)] if _validate_port(config) else [])
    elif engine == "SQLSERVER":
        missing = _missing(config, ["host", "port", "database", "username"])
        errors.extend([_validate_port(config)] if _validate_port(config) else [])
    elif engine == "MONGODB":
        if connection_mode == "URI":
            missing = _missing(config, ["uri", "database"])
        else:
            missing = _missing(config, ["host", "port", "database"])
            errors.extend([_validate_port(config)] if _validate_port(config) else [])
    elif engine == "REDIS":
        missing = _missing(config, ["host", "port"])
        errors.extend([_validate_port(config)] if _validate_port(config) else [])
    elif engine in {"ALIYUN_OSS", "S3", "MINIO"}:
        missing = _missing(config, ["endpoint", "bucket"])
        if engine in {"S3", "MINIO"}:
            # access key may be injected by a credential center later, so v1.0.77 only requires endpoint/bucket.
            pass
    else:
        missing = []
        errors.append(f"暂不支持的资源类型：{engine}")
    if missing:
        errors.append("缺少必要配置：" + "、".join(missing))
    if errors:
        return "CONFIG_INVALID", "；".join(errors)
    return "CONFIG_VALID", "基础配置完整，尚未执行真实连通测试。"


def default_connection_mode(engine: str) -> str:
    if engine == "MONGODB":
        return "URI"
    if engine in {"ALIYUN_OSS", "S3"}:
        return "CLOUD_SERVICE"
    return "HOST_PORT"

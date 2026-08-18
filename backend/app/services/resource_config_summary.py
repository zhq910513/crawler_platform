from __future__ import annotations

from typing import Any

from app.services.resource_config_validator import is_sensitive_key


def mask_config(config: dict[str, Any]) -> dict[str, Any]:
    masked: dict[str, Any] = {}
    for key, value in (config or {}).items():
        if is_sensitive_key(key):
            masked[key] = "******" if value else ""
        else:
            masked[key] = value
    return masked


def build_config_summary(engine: str, connection_mode: str, config: dict[str, Any]) -> dict[str, str]:
    config = config or {}
    if engine in {"MYSQL", "POSTGRESQL", "SQLSERVER"}:
        host = str(config.get("host") or "-")
        port = str(config.get("port") or "-")
        database = str(config.get("database") or "-")
        return {"连接地址": f"{host}:{port}", "数据库": database, "账号": str(config.get("username") or "-"), "密码": "已保存" if config.get("password") else "未保存"}
    if engine == "REDIS":
        host = str(config.get("host") or "-")
        port = str(config.get("port") or "-")
        db = str(config.get("database") if config.get("database") not in (None, "") else "0")
        return {"连接地址": f"{host}:{port}", "库编号": f"db{db}", "账号": str(config.get("username") or "-"), "密码": "已保存" if config.get("password") else "未保存"}
    if engine == "MONGODB":
        if connection_mode == "URI":
            return {"连接方式": "URI", "连接地址": "mongodb://******" if config.get("uri") else "-", "数据库": str(config.get("database") or "-")}
        host = str(config.get("host") or "-")
        port = str(config.get("port") or "-")
        return {"连接地址": f"{host}:{port}", "数据库": str(config.get("database") or "-"), "认证库": str(config.get("authSource") or "admin")}
    if engine in {"ALIYUN_OSS", "S3", "MINIO"}:
        return {"访问地址": str(config.get("endpoint") or "-"), "Bucket": str(config.get("bucket") or "-"), "Region": str(config.get("region") or "-")}
    return {"摘要": "暂不支持的资源类型"}


def build_connection_summary(engine: str, connection_mode: str, config: dict[str, Any]) -> str:
    config = config or {}
    if engine in {"MYSQL", "POSTGRESQL", "SQLSERVER"}:
        return f"{config.get('host') or '-'}:{config.get('port') or '-'} / {config.get('database') or '-'}"
    if engine == "REDIS":
        db = config.get("database") if config.get("database") not in (None, "") else 0
        return f"{config.get('host') or '-'}:{config.get('port') or '-'} / db{db}"
    if engine == "MONGODB":
        if connection_mode == "URI":
            return f"mongodb://****** / {config.get('database') or '-'}"
        return f"{config.get('host') or '-'}:{config.get('port') or '-'} / {config.get('database') or '-'}"
    if engine in {"ALIYUN_OSS", "S3", "MINIO"}:
        return f"{config.get('endpoint') or '-'} / {config.get('bucket') or '-'}"
    return "-"

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CrawlerProjectResourceBinding,
    CrawlerProjectSecretBinding,
    CrawlerResourceConnection,
    CrawlerResourceDatabase,
    CrawlerResourceObject,
    SysSecret,
)
from app.security import decrypt_secret


class ResourceManifestError(RuntimeError):
    pass


def _connection_config(connection: CrawlerResourceConnection) -> dict[str, Any]:
    return dict(connection.config_json or {})


def build_resource_files(
    db: Session,
    *,
    company_id: int,
    project_id: int,
    required_resources: list[str],
) -> tuple[dict[str, Any], dict[str, str]]:
    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "company_id": str(company_id),
        "project_id": str(project_id),
        "mysql": {"connections": {}, "databases": {}, "tables": {}},
        "mongo": {"connections": {}, "databases": {}, "collections": {}},
        "redis": {"connections": {}},
    }
    secrets: dict[str, str] = {}
    resource_bindings = {
        item.logical_name: item
        for item in db.scalars(
            select(CrawlerProjectResourceBinding).where(
                CrawlerProjectResourceBinding.project_id == project_id,
                CrawlerProjectResourceBinding.logical_name.in_(required_resources or ["__none__"]),
            )
        ).all()
    }
    # 连接配置中的 password_secret / uri_secret 可能不是 SpiderEntry 的直接
    # required_resources，因此这里加载当前项目的全部密钥绑定，再只解析实际引用项。
    secret_bindings = {
        item.logical_name: item
        for item in db.scalars(
            select(CrawlerProjectSecretBinding).where(
                CrawlerProjectSecretBinding.project_id == project_id
            )
        ).all()
    }

    connection_cache: dict[int, CrawlerResourceConnection] = {}
    database_cache: dict[int, CrawlerResourceDatabase] = {}

    def add_secret(logical_name: str) -> None:
        binding = secret_bindings.get(logical_name)
        if not binding:
            raise ResourceManifestError(f"缺少项目密钥绑定：{logical_name}")
        secret = db.get(SysSecret, binding.secret_id)
        if (
            not secret
            or not secret.enabled
            or secret.company_id != company_id
            or secret.project_id not in {None, project_id}
        ):
            raise ResourceManifestError(f"密钥不可用或不属于当前项目：{logical_name}")
        secrets[logical_name] = decrypt_secret(secret.encrypted_value)

    def get_connection(connection_id: int) -> CrawlerResourceConnection:
        connection = connection_cache.get(connection_id) or db.get(CrawlerResourceConnection, connection_id)
        if not connection or not connection.enabled or connection.company_id != company_id:
            raise ResourceManifestError("资源连接不存在、已停用或跨公司")
        if connection.project_id not in {None, project_id}:
            raise ResourceManifestError("资源连接属于其他项目")
        connection_cache[connection_id] = connection
        return connection

    def get_database(database_id: int) -> CrawlerResourceDatabase:
        database = database_cache.get(database_id) or db.get(CrawlerResourceDatabase, database_id)
        if not database:
            raise ResourceManifestError("资源数据库不存在")
        get_connection(database.connection_id)
        database_cache[database_id] = database
        return database

    def install_connection(connection: CrawlerResourceConnection, alias: str) -> None:
        cfg = _connection_config(connection)
        kind = connection.resource_type
        if kind == "MYSQL":
            manifest["mysql"]["connections"].setdefault(alias, cfg)
        elif kind == "MONGO":
            manifest["mongo"]["connections"].setdefault(alias, cfg)
        elif kind == "REDIS":
            manifest["redis"]["connections"].setdefault(alias, cfg)
        else:
            raise ResourceManifestError(f"不支持的资源类型：{kind}")
        for key in ("password_secret", "uri_secret"):
            secret_name = cfg.get(key)
            if secret_name and secret_name not in secrets:
                add_secret(str(secret_name))

    for logical_name in required_resources:
        if logical_name in secret_bindings:
            add_secret(logical_name)
            continue
        binding = resource_bindings.get(logical_name)
        if not binding:
            raise ResourceManifestError(f"缺少项目资源绑定：{logical_name}")
        if binding.resource_kind == "CONNECTION" and binding.connection_id:
            connection = get_connection(binding.connection_id)
            install_connection(connection, logical_name)
            continue
        if binding.resource_kind == "DATABASE" and binding.database_id:
            database = get_database(binding.database_id)
            connection = get_connection(database.connection_id)
            conn_alias = f"conn_{connection.connection_id}"
            install_connection(connection, conn_alias)
            if connection.resource_type == "MYSQL":
                manifest["mysql"]["databases"][logical_name] = {
                    "connection": conn_alias,
                    "database": database.database_name,
                    **(database.config_json or {}),
                }
            elif connection.resource_type == "MONGO":
                manifest["mongo"]["databases"][logical_name] = {
                    "connection": conn_alias,
                    "database": database.database_name,
                }
            else:
                raise ResourceManifestError("Redis 不支持数据库对象绑定，请绑定连接")
            continue
        if binding.resource_kind == "OBJECT" and binding.object_id:
            obj = db.get(CrawlerResourceObject, binding.object_id)
            if not obj:
                raise ResourceManifestError(f"资源对象不存在：{logical_name}")
            database = get_database(obj.database_id)
            connection = get_connection(database.connection_id)
            conn_alias = f"conn_{connection.connection_id}"
            db_alias = f"db_{database.database_id}"
            install_connection(connection, conn_alias)
            if connection.resource_type == "MYSQL" and obj.object_type == "TABLE":
                manifest["mysql"]["databases"].setdefault(db_alias, {
                    "connection": conn_alias,
                    "database": database.database_name,
                    **(database.config_json or {}),
                })
                manifest["mysql"]["tables"][logical_name] = {"database": db_alias, "table": obj.object_name}
            elif connection.resource_type == "MONGO" and obj.object_type == "COLLECTION":
                manifest["mongo"]["databases"].setdefault(db_alias, {
                    "connection": conn_alias,
                    "database": database.database_name,
                })
                manifest["mongo"]["collections"][logical_name] = {"database": db_alias, "collection": obj.object_name}
            else:
                raise ResourceManifestError(f"资源类型和对象类型不匹配：{logical_name}")
            continue
        raise ResourceManifestError(f"资源绑定目标无效：{logical_name}")
    return manifest, secrets


def resolve_manifest_secrets(db: Session, project_id: int, manifest: dict[str, Any]) -> dict[str, str]:
    company_id = int(manifest.get("company_id") or 0)
    if not company_id or str(manifest.get("project_id")) != str(project_id):
        raise ResourceManifestError("资源清单公司或项目作用域无效")
    names: set[str] = set()
    for cfg in (manifest.get("mysql", {}).get("connections", {}) or {}).values():
        if cfg.get("password_secret"):
            names.add(str(cfg["password_secret"]))
    for cfg in (manifest.get("mongo", {}).get("connections", {}) or {}).values():
        if cfg.get("uri_secret"):
            names.add(str(cfg["uri_secret"]))
    for cfg in (manifest.get("redis", {}).get("connections", {}) or {}).values():
        if cfg.get("password_secret"):
            names.add(str(cfg["password_secret"]))
    if not names:
        return {}
    bindings = {
        row.logical_name: row
        for row in db.scalars(
            select(CrawlerProjectSecretBinding).where(
                CrawlerProjectSecretBinding.project_id == project_id,
                CrawlerProjectSecretBinding.logical_name.in_(names),
            )
        ).all()
    }
    result: dict[str, str] = {}
    for name in names:
        binding = bindings.get(name)
        if not binding:
            raise ResourceManifestError(f"缺少项目密钥绑定：{name}")
        secret = db.get(SysSecret, binding.secret_id)
        if (
            not secret
            or not secret.enabled
            or secret.company_id != company_id
            or secret.project_id not in {None, project_id}
        ):
            raise ResourceManifestError(f"密钥不可用或不属于当前项目：{name}")
        result[name] = decrypt_secret(secret.encrypted_value)
    return result

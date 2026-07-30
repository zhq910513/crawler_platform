from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import (
    CrawlerProject,
    CrawlerProjectResourceBinding,
    CrawlerProjectSecretBinding,
    CrawlerResourceConnection,
    CrawlerResourceDatabase,
    CrawlerResourceObject,
    SysSecret,
    SysUser,
)
from app.schemas import (
    ProjectResourceBindingUpsert,
    ProjectSecretBindingUpsert,
    ResourceConnectionCreate,
    ResourceDatabaseCreate,
    ResourceObjectCreate,
    ResourceSecretCreate,
)
from app.services.audit import write_operation_log
from app.security import encrypt_secret
from app.services.permissions import require_company_role, require_project_role

router = APIRouter(prefix="/resources", tags=["项目资源"])
SENSITIVE = {"password", "passwd", "pwd", "secret", "token", "cookie", "authorization", "access_key", "private_key", "uri"}


def _contains_sensitive(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            name = str(key).lower()
            if any(part in name for part in SENSITIVE):
                # 只允许保存对逻辑密钥的引用字段，而不是明文值。
                if name in {"password_secret", "uri_secret"} and isinstance(child, str) and child:
                    continue
                return True
            if _contains_sensitive(child):
                return True
    elif isinstance(value, list):
        return any(_contains_sensitive(item) for item in value)
    return False


def _flush_or_conflict(db: Session, message: str) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=message) from exc


def connection_dict(row: CrawlerResourceConnection) -> dict:
    return {
        "connection_id": row.connection_id,
        "company_id": row.company_id,
        "project_id": row.project_id,
        "connection_code": row.connection_code,
        "connection_name": row.connection_name,
        "resource_type": row.resource_type,
        "config": row.config_json,
        "enabled": row.enabled,
    }


@router.post("/secrets")
def create_resource_secret(
    payload: ResourceSecretCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    if payload.project_id:
        project = db.get(CrawlerProject, payload.project_id)
        if not project or project.company_id != payload.company_id:
            raise HTTPException(status_code=409, detail="项目与公司不匹配")
        require_project_role(db, user, payload.project_id, "OWNER")
    else:
        require_company_role(db, user, payload.company_id, "ADMIN")
    if db.scalar(select(SysSecret).where(SysSecret.secret_code == payload.secret_code)):
        raise HTTPException(status_code=409, detail="密钥编码已存在")
    row = SysSecret(
        company_id=payload.company_id,
        project_id=payload.project_id,
        secret_code=payload.secret_code,
        secret_name=payload.secret_name,
        encrypted_value=encrypt_secret(payload.value),
        description=payload.description,
        enabled=payload.enabled,
    )
    db.add(row)
    _flush_or_conflict(db, "密钥编码已存在")
    write_operation_log(
        db, request, user, "CREATE", "RESOURCE_SECRET", row.secret_id,
        after_data={"secret_code": row.secret_code, "company_id": row.company_id, "project_id": row.project_id},
    )
    db.commit()
    return {
        "secret_id": row.secret_id,
        "secret_code": row.secret_code,
        "secret_name": row.secret_name,
        "company_id": row.company_id,
        "project_id": row.project_id,
        "enabled": row.enabled,
    }


@router.post("/connections")
def create_connection(
    payload: ResourceConnectionCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    if payload.project_id:
        project = db.get(CrawlerProject, payload.project_id)
        if not project or project.company_id != payload.company_id:
            raise HTTPException(status_code=409, detail="项目与公司不匹配")
        require_project_role(db, user, payload.project_id, "OWNER")
    else:
        require_company_role(db, user, payload.company_id, "ADMIN")
    if _contains_sensitive(payload.config):
        raise HTTPException(status_code=400, detail="连接配置禁止保存密码、Token、Cookie、URI 等敏感明文，请使用逻辑密钥引用")
    duplicate = db.scalar(select(CrawlerResourceConnection).where(
        CrawlerResourceConnection.company_id == payload.company_id,
        CrawlerResourceConnection.project_id == payload.project_id,
        CrawlerResourceConnection.connection_code == payload.connection_code,
    ))
    if duplicate:
        raise HTTPException(status_code=409, detail="连接编码已存在")
    row = CrawlerResourceConnection(
        company_id=payload.company_id,
        project_id=payload.project_id,
        connection_code=payload.connection_code,
        connection_name=payload.connection_name,
        resource_type=payload.resource_type,
        config_json=payload.config,
        enabled=payload.enabled,
    )
    db.add(row)
    _flush_or_conflict(db, "连接编码已存在")
    write_operation_log(db, request, user, "CREATE", "RESOURCE_CONNECTION", row.connection_id, after_data=payload.model_dump())
    db.commit()
    return connection_dict(row)


@router.post("/databases")
def create_database(
    payload: ResourceDatabaseCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    connection = db.get(CrawlerResourceConnection, payload.connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="资源连接不存在")
    if connection.project_id:
        require_project_role(db, user, connection.project_id, "OWNER")
    else:
        require_company_role(db, user, connection.company_id, "ADMIN")
    if connection.resource_type == "REDIS":
        raise HTTPException(status_code=400, detail="Redis 连接不创建逻辑数据库对象，请直接绑定连接")
    if _contains_sensitive(payload.config):
        raise HTTPException(status_code=400, detail="数据库配置禁止保存敏感明文，请使用逻辑密钥引用")
    duplicate = db.scalar(select(CrawlerResourceDatabase).where(
        CrawlerResourceDatabase.connection_id == connection.connection_id,
        CrawlerResourceDatabase.database_code == payload.database_code,
    ))
    if duplicate:
        raise HTTPException(status_code=409, detail="数据库编码已存在")
    row = CrawlerResourceDatabase(
        connection_id=connection.connection_id,
        database_code=payload.database_code,
        database_name=payload.database_name,
        config_json=payload.config,
    )
    db.add(row)
    _flush_or_conflict(db, "数据库编码已存在")
    write_operation_log(db, request, user, "CREATE", "RESOURCE_DATABASE", row.database_id, after_data=payload.model_dump())
    db.commit()
    return {"database_id": row.database_id, "connection_id": row.connection_id, "database_code": row.database_code, "database_name": row.database_name, "config": row.config_json}


@router.post("/objects")
def create_object(
    payload: ResourceObjectCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    database = db.get(CrawlerResourceDatabase, payload.database_id)
    if not database:
        raise HTTPException(status_code=404, detail="资源数据库不存在")
    connection = db.get(CrawlerResourceConnection, database.connection_id)
    if connection.project_id:
        require_project_role(db, user, connection.project_id, "OWNER")
    else:
        require_company_role(db, user, connection.company_id, "ADMIN")
    if connection.resource_type == "MYSQL" and payload.object_type != "TABLE":
        raise HTTPException(status_code=400, detail="MySQL 对象类型必须是 TABLE")
    if connection.resource_type == "MONGO" and payload.object_type != "COLLECTION":
        raise HTTPException(status_code=400, detail="MongoDB 对象类型必须是 COLLECTION")
    if connection.resource_type not in {"MYSQL", "MONGO"}:
        raise HTTPException(status_code=400, detail="当前连接类型不支持表或 Collection")
    duplicate = db.scalar(select(CrawlerResourceObject).where(
        CrawlerResourceObject.database_id == database.database_id,
        CrawlerResourceObject.object_code == payload.object_code,
    ))
    if duplicate:
        raise HTTPException(status_code=409, detail="资源对象编码已存在")
    row = CrawlerResourceObject(database_id=database.database_id, object_code=payload.object_code, object_name=payload.object_name, object_type=payload.object_type)
    db.add(row)
    _flush_or_conflict(db, "资源对象编码已存在")
    write_operation_log(db, request, user, "CREATE", "RESOURCE_OBJECT", row.object_id, after_data=payload.model_dump())
    db.commit()
    return {"object_id": row.object_id, "database_id": row.database_id, "object_code": row.object_code, "object_name": row.object_name, "object_type": row.object_type}


@router.get("/companies/{company_id}/catalog")
def company_catalog(
    company_id: int,
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> list[dict]:
    if project_id:
        project = db.get(CrawlerProject, project_id)
        if not project or project.company_id != company_id:
            raise HTTPException(status_code=404, detail="项目不存在或不属于当前公司")
        require_project_role(db, user, project_id, "VIEWER")
        scope_condition = (CrawlerResourceConnection.project_id.is_(None)) | (CrawlerResourceConnection.project_id == project_id)
    else:
        require_company_role(db, user, company_id, "MEMBER")
        scope_condition = CrawlerResourceConnection.project_id.is_(None)
    connections = db.scalars(
        select(CrawlerResourceConnection).where(
            CrawlerResourceConnection.company_id == company_id,
            scope_condition,
        ).order_by(CrawlerResourceConnection.connection_id)
    ).all()
    result = []
    for connection in connections:
        databases = db.scalars(select(CrawlerResourceDatabase).where(CrawlerResourceDatabase.connection_id == connection.connection_id).order_by(CrawlerResourceDatabase.database_id)).all()
        db_items = []
        for database in databases:
            objects = db.scalars(select(CrawlerResourceObject).where(CrawlerResourceObject.database_id == database.database_id).order_by(CrawlerResourceObject.object_id)).all()
            db_items.append({
                "database_id": database.database_id,
                "database_code": database.database_code,
                "database_name": database.database_name,
                "objects": [{"object_id": x.object_id, "object_code": x.object_code, "object_name": x.object_name, "object_type": x.object_type} for x in objects],
            })
        result.append(connection_dict(connection) | {"databases": db_items})
    return result


@router.get("/projects/{project_id}/bindings")
def project_bindings(project_id: int, db: Session = Depends(get_db), user: SysUser = Depends(get_current_user)) -> dict:
    require_project_role(db, user, project_id, "VIEWER")
    resources = db.scalars(select(CrawlerProjectResourceBinding).where(CrawlerProjectResourceBinding.project_id == project_id).order_by(CrawlerProjectResourceBinding.logical_name)).all()
    secrets = db.scalars(select(CrawlerProjectSecretBinding).where(CrawlerProjectSecretBinding.project_id == project_id).order_by(CrawlerProjectSecretBinding.logical_name)).all()
    return {
        "resources": [{
            "binding_id": x.binding_id,
            "logical_name": x.logical_name,
            "resource_kind": x.resource_kind,
            "connection_id": x.connection_id,
            "database_id": x.database_id,
            "object_id": x.object_id,
        } for x in resources],
        "secrets": [{"binding_id": x.binding_id, "logical_name": x.logical_name, "secret_id": x.secret_id} for x in secrets],
    }


@router.put("/projects/{project_id}/bindings")
def replace_project_bindings(
    project_id: int,
    payload: list[ProjectResourceBindingUpsert],
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    require_project_role(db, user, project_id, "OWNER")
    project = db.get(CrawlerProject, project_id)
    logical_names = [item.logical_name for item in payload]
    if len(logical_names) != len(set(logical_names)):
        raise HTTPException(status_code=409, detail="资源逻辑名称不能重复")
    db.execute(delete(CrawlerProjectResourceBinding).where(CrawlerProjectResourceBinding.project_id == project_id))
    for item in payload:
        connection = db.get(CrawlerResourceConnection, item.connection_id) if item.connection_id else None
        database = db.get(CrawlerResourceDatabase, item.database_id) if item.database_id else None
        obj = db.get(CrawlerResourceObject, item.object_id) if item.object_id else None
        target_connection = connection
        if database:
            target_connection = db.get(CrawlerResourceConnection, database.connection_id)
        if obj:
            database = db.get(CrawlerResourceDatabase, obj.database_id)
            target_connection = db.get(CrawlerResourceConnection, database.connection_id)
        if not target_connection or target_connection.company_id != project.company_id or target_connection.project_id not in {None, project_id}:
            raise HTTPException(status_code=409, detail=f"资源 {item.logical_name} 不属于当前项目或公司")
        db.add(CrawlerProjectResourceBinding(
            project_id=project_id,
            logical_name=item.logical_name,
            resource_kind=item.resource_kind,
            connection_id=item.connection_id if item.resource_kind == "CONNECTION" else None,
            database_id=item.database_id if item.resource_kind == "DATABASE" else None,
            object_id=item.object_id if item.resource_kind == "OBJECT" else None,
        ))
    write_operation_log(db, request, user, "REPLACE_BINDINGS", "PROJECT", project_id, after_data={"count": len(payload)})
    db.commit()
    return {"ok": True, "count": len(payload)}


@router.get("/projects/{project_id}/secret-options")
def secret_options(project_id: int, db: Session = Depends(get_db), user: SysUser = Depends(get_current_user)) -> list[dict]:
    require_project_role(db, user, project_id, "OWNER")
    project = db.get(CrawlerProject, project_id)
    rows = db.scalars(
        select(SysSecret).where(
            SysSecret.enabled.is_(True),
            SysSecret.company_id == project.company_id,
            (SysSecret.project_id.is_(None)) | (SysSecret.project_id == project_id),
        ).order_by(SysSecret.secret_code)
    ).all()
    return [{
        "secret_id": x.secret_id,
        "secret_code": x.secret_code,
        "secret_name": x.secret_name,
        "scope": "PROJECT" if x.project_id else "COMPANY",
    } for x in rows]


@router.put("/projects/{project_id}/secret-bindings")
def replace_secret_bindings(
    project_id: int,
    payload: list[ProjectSecretBindingUpsert],
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    require_project_role(db, user, project_id, "OWNER")
    project = db.get(CrawlerProject, project_id)
    logical_names = [item.logical_name for item in payload]
    if len(logical_names) != len(set(logical_names)):
        raise HTTPException(status_code=409, detail="密钥逻辑名称不能重复")
    db.execute(delete(CrawlerProjectSecretBinding).where(CrawlerProjectSecretBinding.project_id == project_id))
    for item in payload:
        secret = db.get(SysSecret, item.secret_id)
        if (
            not secret
            or not secret.enabled
            or secret.company_id != project.company_id
            or secret.project_id not in {None, project_id}
        ):
            raise HTTPException(status_code=409, detail=f"密钥不可用或不属于当前项目：{item.logical_name}")
        db.add(CrawlerProjectSecretBinding(project_id=project_id, logical_name=item.logical_name, secret_id=item.secret_id))
    write_operation_log(db, request, user, "REPLACE_SECRET_BINDINGS", "PROJECT", project_id, after_data={"count": len(payload)})
    db.commit()
    return {"ok": True, "count": len(payload)}

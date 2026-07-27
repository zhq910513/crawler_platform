from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin
from app.models import SysConfig, SysSecret, SysUser
from app.security import encrypt_secret
from app.services.audit import write_operation_log

router = APIRouter(prefix="/settings", tags=["系统设置"])


@router.get("/configs")
def list_configs(db: Session = Depends(get_db), _: SysUser = Depends(require_admin)) -> list[dict]:
    rows = db.scalars(select(SysConfig).order_by(SysConfig.config_key.asc())).all()
    return [{"config_id": row.config_id, "config_key": row.config_key, "config_name": row.config_name, "config_value": row.config_value, "description": row.description} for row in rows]


@router.put("/configs/{config_key}")
def set_config(config_key: str, payload: dict, request: Request, db: Session = Depends(get_db), user: SysUser = Depends(require_admin)) -> dict:
    row = db.scalar(select(SysConfig).where(SysConfig.config_key == config_key))
    before = {"config_value": row.config_value} if row else None
    if not row:
        row = SysConfig(config_key=config_key, config_name=payload.get("config_name", config_key), config_value=str(payload.get("config_value", "")), description=payload.get("description", ""))
        db.add(row)
    else:
        row.config_name = payload.get("config_name", row.config_name)
        row.config_value = str(payload.get("config_value", row.config_value))
        row.description = payload.get("description", row.description)
    db.flush()
    write_operation_log(db, request, user, "SET_CONFIG", "CONFIG", row.config_id, before, {"config_key": row.config_key, "config_value": row.config_value})
    db.commit()
    return {"config_key": row.config_key, "config_value": row.config_value}


@router.get("/secrets")
def list_secrets(db: Session = Depends(get_db), _: SysUser = Depends(require_admin)) -> list[dict]:
    rows = db.scalars(select(SysSecret).order_by(SysSecret.secret_code.asc())).all()
    return [{"secret_id": row.secret_id, "secret_code": row.secret_code, "secret_name": row.secret_name, "description": row.description, "enabled": row.enabled, "updated_at": row.updated_at} for row in rows]


@router.put("/secrets/{secret_code}")
def set_secret(secret_code: str, payload: dict, request: Request, db: Session = Depends(get_db), user: SysUser = Depends(require_admin)) -> dict:
    value = payload.get("value")
    row = db.scalar(select(SysSecret).where(SysSecret.secret_code == secret_code))
    if not row and not value:
        raise HTTPException(status_code=400, detail="新建密钥时必须提供 value")
    if not row:
        row = SysSecret(secret_code=secret_code, secret_name=payload.get("secret_name", secret_code), encrypted_value=encrypt_secret(str(value)), description=payload.get("description", ""), enabled=bool(payload.get("enabled", True)))
        db.add(row)
    else:
        row.secret_name = payload.get("secret_name", row.secret_name)
        row.description = payload.get("description", row.description)
        row.enabled = bool(payload.get("enabled", row.enabled))
        if value:
            row.encrypted_value = encrypt_secret(str(value))
    db.flush()
    write_operation_log(db, request, user, "SET_SECRET", "SECRET", row.secret_id, after_data={"secret_code": row.secret_code, "enabled": row.enabled})
    db.commit()
    return {"secret_code": row.secret_code, "secret_name": row.secret_name, "enabled": row.enabled}

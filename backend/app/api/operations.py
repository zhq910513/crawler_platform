from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin
from app.models import SysOperationLog, SysUser

router = APIRouter(prefix="/operations", tags=["操作日志"])


@router.get("")
def list_operations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=200),
    db: Session = Depends(get_db),
    _: SysUser = Depends(require_admin),
) -> dict:
    total = db.scalar(select(func.count(SysOperationLog.operation_id))) or 0
    rows = db.scalars(select(SysOperationLog).order_by(SysOperationLog.operation_id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "total": total,
        "items": [
            {
                "operation_id": row.operation_id,
                "user_name": row.user_name,
                "operation_type": row.operation_type,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "request_method": row.request_method,
                "request_path": row.request_path,
                "ip_address": row.ip_address,
                "status": row.status,
                "error_message": row.error_message,
                "created_at": row.created_at,
            }
            for row in rows
        ],
        "page": page,
        "page_size": page_size,
    }

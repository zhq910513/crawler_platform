from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SysUser
from app.responses import ok
from app.schemas import AgentRegistration, ServerCreate, ServerUpdate
from app.services.server_service import ServerService

router = APIRouter(prefix="/servers", tags=["服务器"])


@router.get("")
def list_servers(company_id: int | None = Query(default=None), user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ServerService(db).list_servers(user, company_id))


@router.post("")
def create_server(payload: ServerCreate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ServerService(db).create_server(user, payload))


@router.patch("/{server_id}")
def update_server(server_id: int, payload: ServerUpdate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ServerService(db).update_server(user, server_id, payload))

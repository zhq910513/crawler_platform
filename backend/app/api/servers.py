from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SysUser
from app.responses import ok
from app.schemas import AgentJoinTokenCreate, AgentRegistration, ServerCreate, ServerUpdate
from app.services.server_service import ServerService

router = APIRouter(prefix="/servers", tags=["执行节点"])


def _detected_base_url(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    if forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}".rstrip("/")
    return str(request.base_url).rstrip("/")


@router.get("")
def list_servers(company_id: int | None = Query(default=None), user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ServerService(db).list_servers(user, company_id))


@router.post("")
def create_server(payload: ServerCreate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ServerService(db).create_server(user, payload))


@router.patch("/{server_id}")
def update_server(server_id: int, payload: ServerUpdate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ServerService(db).update_server(user, server_id, payload))


@router.post("/agent-join-tokens")
def create_agent_join_token(payload: AgentJoinTokenCreate, request: Request, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ServerService(db).create_agent_join_token(user, payload, _detected_base_url(request)))


@router.get("/agent-join-tokens")
def list_agent_join_tokens(company_id: int | None = Query(default=None), user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ServerService(db).list_agent_join_tokens(user, company_id))

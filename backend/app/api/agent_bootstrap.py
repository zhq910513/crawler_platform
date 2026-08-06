from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import AgentBootstrapEnvRequest
from app.services.server_service import ServerService

router = APIRouter(tags=["Agent 接入"])


@router.get("/agent-installers/linux.sh", response_class=PlainTextResponse)
def get_linux_agent_installer() -> PlainTextResponse:
    script_path = Path(__file__).resolve().parents[3] / "deploy" / "scripts" / "install-agent.sh"
    return PlainTextResponse(script_path.read_text(encoding="utf-8"), media_type="text/x-shellscript; charset=utf-8")


@router.post("/agent-bootstrap/env", response_class=PlainTextResponse)
def create_agent_bootstrap_env(payload: AgentBootstrapEnvRequest, db: Session = Depends(get_db)) -> PlainTextResponse:
    content = ServerService(db).consume_agent_join_token(payload)
    return PlainTextResponse(content, media_type="text/plain; charset=utf-8")


@router.get("/agent-bootstrap/ping")
def ping_agent_bootstrap():
    return {"code": 200, "message": "success", "data": {"ok": True}}

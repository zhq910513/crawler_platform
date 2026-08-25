from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_agent
from app.models import CrawlerAgent
from app.schemas import AgentBootstrapEnvRequest, AgentBootstrapFailureReport, AgentBootstrapPrecheckRequest
from app.services.server_service import ServerService
from app.services.system_config_service import SystemConfigService

router = APIRouter(tags=["Agent 接入"])


def _shell_double_quote_value(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace("\"", "\\\"").replace("$", "\\$").replace("`", "\\`")


def _installer_script_path() -> Path:
    # API 镜像只复制 backend/app，不能依赖仓库根目录的 deploy/scripts。
    # 因此安装脚本模板随后端代码一起打包，避免生产环境 /api/v1/agent-installers/linux.sh 返回 500。
    return Path(__file__).resolve().parents[1] / "templates" / "install-agent.sh"


@router.get("/agent-installers/linux.sh", response_class=PlainTextResponse)
def get_linux_agent_installer() -> PlainTextResponse:
    script_path = _installer_script_path()
    script = script_path.read_text(encoding="utf-8")
    script = script.replace("__CRAWLER_AGENT_IMAGE__", _shell_double_quote_value(settings.crawler_agent_image))
    return PlainTextResponse(script, media_type="text/x-shellscript; charset=utf-8")


@router.post("/agent-bootstrap/precheck")
def precheck_agent_bootstrap(payload: AgentBootstrapPrecheckRequest, db: Session = Depends(get_db)):
    return ServerService(db).precheck_agent_join_token(payload.join_token)


@router.post("/agent-bootstrap/env", response_class=PlainTextResponse)
def create_agent_bootstrap_env(payload: AgentBootstrapEnvRequest, request: Request, db: Session = Depends(get_db)) -> PlainTextResponse:
    detected = SystemConfigService.detected_base_url_from_request(request)
    content = ServerService(db).consume_agent_join_token(payload, detected)
    return PlainTextResponse(content, media_type="text/plain; charset=utf-8")


@router.get("/agent-bootstrap/resume-env", response_class=PlainTextResponse)
def resume_agent_bootstrap_env(
    request: Request,
    join_token: str = Query("", alias="joinToken"),
    hostname: str = Query(""),
    host_ip: str = Query("", alias="hostIp"),
    public_ip: str = Query("", alias="publicIp"),
    agent: CrawlerAgent = Depends(get_agent),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    detected = SystemConfigService.detected_base_url_from_request(request)
    content = ServerService(db).resume_agent_bootstrap_env(agent, detected, join_token, hostname=hostname, host_ip=host_ip, public_ip=public_ip)
    return PlainTextResponse(content, media_type="text/plain; charset=utf-8")




@router.post("/agent-bootstrap/failures")
def report_agent_bootstrap_failure(payload: AgentBootstrapFailureReport, db: Session = Depends(get_db)):
    return ServerService(db).report_agent_join_failure(payload)


@router.get("/agent-bootstrap/ping")
def ping_agent_bootstrap():
    return {"code": 200, "message": "success", "data": {"ok": True}}

from __future__ import annotations

import secrets
from datetime import timedelta
from fastapi import status
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import CrawlerAgent, CrawlerAgentJoinToken, CrawlerServer, SysUser
from app.repositories.platform import AgentRepository, CompanyRepository, ServerRepository
from app.schemas import AgentBootstrapEnvRequest, AgentJoinTokenCreate, AgentRegistration, ServerCreate, ServerUpdate
from app.security import hash_password
from app.services.permissions import require_company_scope, require_super_admin, scoped_company_id
from app.services.audit import write_operation_log
from app.config import settings
from app.utils import sha256_text, utcnow


class ServerService:
    def __init__(self, db: Session):
        self.db = db
        self.servers = ServerRepository(db)
        self.agents = AgentRepository(db)
        self.companies = CompanyRepository(db)

    def list_servers(self, user: SysUser, company_id: int | None = None) -> list[CrawlerServer]:
        scoped = scoped_company_id(user, company_id)
        servers = self.servers.list_servers(scoped)
        offline_before = utcnow() - timedelta(seconds=max(30, settings.agent_lease_seconds * 2))
        changed = False
        for server in servers:
            agent = server.agent
            if agent and agent.last_heartbeat_at and agent.last_heartbeat_at < offline_before:
                if agent.connection_status != "OFFLINE" or server.health_status != "OFFLINE":
                    agent.connection_status = "OFFLINE"
                    server.health_status = "OFFLINE"
                    metrics = dict(server.metrics or {})
                    metrics["lastError"] = metrics.get("lastError") or "Agent 心跳超时，节点已离线"
                    server.metrics = metrics
                    changed = True
        if changed:
            self.db.commit()
        return servers

    def create_server(self, user: SysUser, payload: ServerCreate) -> CrawlerServer:
        require_super_admin(user)
        if not self.companies.get(payload.company_id):
            raise AppError("公司不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        if self.servers.by_code(payload.server_code):
            raise AppError("服务器编码已存在", code=40031)
        server = CrawlerServer(**payload.model_dump())
        self.servers.add(server)
        self.db.flush()
        write_operation_log(self.db, user, None, operation_type="CREATE_SERVER", resource_type="server", resource_id=str(server.server_id), after_data={"serverId": server.server_id, "serverCode": server.server_code, "companyId": server.company_id})
        self.db.commit()
        return server

    def update_server(self, user: SysUser, server_id: int, payload: ServerUpdate) -> CrawlerServer:
        server = self.servers.get(server_id)
        if not server:
            raise AppError("资源不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        require_company_scope(user, server.company_id)
        if not user.role_type == "SUPER_ADMIN":
            raise AppError("普通用户不能修改 Agent 节点", code=40331, http_status=status.HTTP_403_FORBIDDEN)
        before = {c.name: getattr(server, c.name) for c in server.__table__.columns}
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(server, key, value)
        after = {c.name: getattr(server, c.name) for c in server.__table__.columns}
        write_operation_log(self.db, user, None, operation_type="UPDATE_SERVER", resource_type="server", resource_id=str(server.server_id), before_data=before, after_data=after)
        self.db.commit()
        return server

    def create_agent_join_token(self, user: SysUser, payload: AgentJoinTokenCreate) -> dict:
        require_super_admin(user)
        if not self.companies.get(payload.company_id):
            raise AppError("公司不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        exists = self.servers.by_code(payload.server_code)
        if exists and exists.company_id != payload.company_id:
            raise AppError("服务器编码已被其他公司使用", code=40032)
        agent = self.agents.by_code(payload.agent_code)
        if agent and agent.company_id != payload.company_id:
            raise AppError("Agent 编码已被其他公司使用", code=40033)
        raw_token = secrets.token_urlsafe(40)
        expires_at = utcnow() + timedelta(hours=payload.expires_in_hours)
        token = CrawlerAgentJoinToken(
            company_id=payload.company_id,
            token_hash=sha256_text(raw_token),
            token_name=f"{payload.server_name} Agent 接入令牌",
            server_code=payload.server_code,
            server_name=payload.server_name,
            agent_code=payload.agent_code,
            agent_name=payload.agent_name or payload.server_name,
            max_container_slots=payload.max_container_slots,
            work_dir=payload.work_dir,
            labels=payload.labels or {},
            capabilities=payload.capabilities or {},
            registry_credential_ref=payload.registry_credential_ref,
            install_mode=payload.install_mode,
            expires_at=expires_at,
            created_by=user.user_id,
        )
        self.db.add(token)
        self.db.flush()
        command = self._install_command(raw_token)
        write_operation_log(self.db, user, None, operation_type="CREATE_AGENT_JOIN_TOKEN", resource_type="agent", resource_id=str(token.token_id), after_data={"tokenId": token.token_id, "companyId": token.company_id, "agentCode": token.agent_code, "serverCode": token.server_code})
        self.db.commit()
        return {
            "tokenId": token.token_id,
            "companyId": token.company_id,
            "agentCode": token.agent_code,
            "serverCode": token.server_code,
            "expiresAt": token.expires_at,
            "joinToken": raw_token,
            "installCommand": command,
            "note": "该命令会先做平台端口、Docker、权限、磁盘、镜像仓库等初检；令牌只展示一次，请妥善保存。",
        }

    def list_agent_join_tokens(self, user: SysUser, company_id: int | None = None) -> list[dict]:
        scoped = scoped_company_id(user, company_id)
        from sqlalchemy import select
        rows = list(self.db.scalars(select(CrawlerAgentJoinToken).where(CrawlerAgentJoinToken.company_id == scoped).order_by(CrawlerAgentJoinToken.created_at.desc())).all())
        return [{**{c.name: getattr(row, c.name) for c in row.__table__.columns}, "tokenHash": "***"} for row in rows]

    def consume_agent_join_token(self, payload: AgentBootstrapEnvRequest) -> str:
        from sqlalchemy import select
        token = self.db.scalar(select(CrawlerAgentJoinToken).where(CrawlerAgentJoinToken.token_hash == sha256_text(payload.join_token), CrawlerAgentJoinToken.status == "ACTIVE"))
        if not token:
            raise AppError("Agent 接入令牌无效或已使用", code=40160, http_status=status.HTTP_401_UNAUTHORIZED)
        if token.expires_at and token.expires_at < utcnow():
            token.status = "EXPIRED"
            self.db.commit()
            raise AppError("Agent 接入令牌已过期", code=40161, http_status=status.HTTP_401_UNAUTHORIZED)
        server = self.servers.by_code(token.server_code)
        if not server:
            server = CrawlerServer(
                company_id=token.company_id,
                server_code=token.server_code,
                server_name=token.server_name,
                max_container_slots=token.max_container_slots,
                labels=token.labels or {},
                capabilities=token.capabilities or {},
                registry_credential_ref=token.registry_credential_ref,
                work_dir=token.work_dir,
                manage_status="ENABLED",
            )
            self.servers.add(server)
            self.db.flush()
        elif server.company_id != token.company_id:
            raise AppError("服务器编码已被其他公司使用", code=40032)
        else:
            server.server_name = token.server_name or server.server_name
            server.max_container_slots = token.max_container_slots
            server.labels = token.labels or server.labels or {}
            server.capabilities = token.capabilities or server.capabilities or {}
            server.registry_credential_ref = token.registry_credential_ref or server.registry_credential_ref
            server.work_dir = token.work_dir or server.work_dir
        raw_agent_token = secrets.token_urlsafe(36)
        agent = self.agents.by_code(token.agent_code)
        if agent and agent.server_id != server.server_id:
            raise AppError("Agent 编码已绑定其他服务器", code=40033)
        if not agent:
            agent = CrawlerAgent(
                company_id=token.company_id,
                server_id=server.server_id,
                agent_code=token.agent_code,
                agent_name=token.agent_name or token.server_name,
                token_hash=sha256_text(raw_agent_token),
                connection_status="UNREGISTERED",
                capabilities=token.capabilities or {},
            )
            self.agents.add(agent)
        else:
            agent.token_hash = sha256_text(raw_agent_token)
            agent.agent_name = token.agent_name or agent.agent_name
            agent.capabilities = token.capabilities or agent.capabilities or {}
        token.status = "USED"
        token.used_at = utcnow()
        token.last_preflight_report = payload.install_report or {}
        self.db.commit()
        lines = {
            "AGENT_PLATFORM_URL": settings.platform_public_url or "",
            "AGENT_AGENT_TOKEN": raw_agent_token,
            "AGENT_AGENT_CODE": token.agent_code,
            "AGENT_SERVER_CODE": token.server_code,
            "AGENT_MAX_SLOTS": str(token.max_container_slots),
            "AGENT_PROJECT_DATA_ROOT": token.work_dir.rstrip("/") + "/projects",
            "AGENT_RUN_ROOT": token.work_dir.rstrip("/") + "/runs",
            "AGENT_SPOOL_DIR": token.work_dir.rstrip("/") + "/spool",
            "AGENT_CAPABILITIES_JSON": __import__('json').dumps(token.capabilities or {}, ensure_ascii=False),
        }
        return "\n".join(f"{k}={self._quote_env(v)}" for k, v in lines.items()) + "\n"

    def _install_command(self, token: str) -> str:
        base = settings.platform_public_url or "http://127.0.0.1:8000"
        return f"curl -fsSL {base.rstrip('/')}/api/v1/agent-installers/linux.sh | bash -s -- --platform-url {base.rstrip('/')} --join-token {token}"

    @staticmethod
    def _quote_env(value) -> str:
        text = str(value or "")
        return "'" + text.replace("'", "'\\''") + "'"

    def register_agent(self, user: SysUser, payload: AgentRegistration) -> dict:
        require_super_admin(user)
        if not self.companies.get(payload.company_id):
            raise AppError("公司不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        server = self.servers.by_code(payload.server_code)
        if not server:
            server = CrawlerServer(
                company_id=payload.company_id,
                server_code=payload.server_code,
                server_name=payload.server_name,
                server_ip=payload.server_ip,
                max_container_slots=payload.max_container_slots,
                manage_status="ENABLED",
            )
            self.servers.add(server)
        elif server.company_id != payload.company_id:
            raise AppError("服务器编码已被其他公司使用", code=40032)
        agent = self.agents.by_code(payload.agent_code)
        if agent and agent.server_id != server.server_id:
            raise AppError("Agent 编码已绑定其他服务器", code=40033)
        raw_token = secrets.token_urlsafe(36)
        if not agent:
            agent = CrawlerAgent(
                company_id=payload.company_id,
                server_id=server.server_id,
                agent_code=payload.agent_code,
                agent_name=payload.agent_name,
                token_hash=sha256_text(raw_token),
                connection_status="UNREGISTERED",
            )
            self.agents.add(agent)
        else:
            agent.token_hash = sha256_text(raw_token)
            agent.agent_name = payload.agent_name or agent.agent_name
        self.db.flush()
        write_operation_log(self.db, user, None, operation_type="REGISTER_AGENT", resource_type="agent", resource_id=str(agent.agent_id), after_data={"agentId": agent.agent_id, "agentCode": agent.agent_code, "serverId": server.server_id, "companyId": payload.company_id})
        self.db.commit()
        return {"agent": {"agentId": agent.agent_id, "agentCode": agent.agent_code, "agentName": agent.agent_name, "connectionStatus": agent.connection_status, "serverId": agent.server_id}, "server": server, "agentToken": raw_token}

from __future__ import annotations

import secrets
from fastapi import status
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import CrawlerAgent, CrawlerServer, SysUser
from app.repositories.platform import AgentRepository, CompanyRepository, ServerRepository
from app.schemas import AgentRegistration, ServerCreate, ServerUpdate
from app.security import hash_password
from app.services.permissions import require_company_scope, require_super_admin, scoped_company_id
from app.services.audit import write_operation_log
from app.utils import sha256_text


class ServerService:
    def __init__(self, db: Session):
        self.db = db
        self.servers = ServerRepository(db)
        self.agents = AgentRepository(db)
        self.companies = CompanyRepository(db)

    def list_servers(self, user: SysUser, company_id: int | None = None) -> list[CrawlerServer]:
        scoped = scoped_company_id(user, company_id)
        return self.servers.list_servers(scoped)

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

from __future__ import annotations

import secrets
import shlex
from datetime import timedelta
from urllib.parse import urlparse
from fastapi import status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import (
    CrawlerAgent,
    CrawlerAgentJoinToken,
    CrawlerDiscoveredProjectServer,
    CrawlerOfflineRunSnapshot,
    CrawlerProjectDeploymentTarget,
    CrawlerProjectServer,
    CrawlerRunContainerSnapshot,
    CrawlerServer,
    CrawlerTaskRun,
    SysUser,
)
from app.repositories.platform import AgentRepository, CompanyRepository, ServerRepository
from app.schemas import AgentBootstrapEnvRequest, AgentJoinTokenCreate, AgentRegistration, ServerCreate, ServerUpdate
from app.security import hash_password
from app.services.permissions import require_company_scope, scoped_company_id, writable_company_id
from app.services.audit import write_operation_log
from app.config import settings
from app.services.system_config_service import SystemConfigService
from app.utils import sha256_text, utcnow


class ServerService:
    def __init__(self, db: Session):
        self.db = db
        self.servers = ServerRepository(db)
        self.agents = AgentRepository(db)
        self.companies = CompanyRepository(db)

    def list_servers(self, user: SysUser, company_id: int | None = None) -> list[dict]:
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
        return [self._server_payload(server) for server in servers]

    def _server_payload(self, server: CrawlerServer) -> dict:
        agent = server.agent
        metrics = dict(server.metrics or {})
        if agent:
            metrics.setdefault("lastHeartbeatAt", agent.last_heartbeat_at)
            metrics.setdefault("lastError", agent.last_error or metrics.get("lastError") or "")
        return {
            **{c.name: getattr(server, c.name) for c in server.__table__.columns},
            "agent_code": agent.agent_code if agent else "",
            "agent_name": agent.agent_name if agent else "",
            "agent_connection_status": agent.connection_status if agent else "UNREGISTERED",
            "agent_version": agent.agent_version if agent else "",
            "agent_last_heartbeat_at": agent.last_heartbeat_at if agent else None,
            "agent_last_error": agent.last_error if agent else "",
            "metrics": metrics,
        }

    def create_server(self, user: SysUser, payload: ServerCreate) -> CrawlerServer:
        company_id = writable_company_id(user, payload.company_id)
        if not self.companies.get(company_id):
            raise AppError("公司不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        exists = self.servers.by_code(payload.server_code)
        if exists:
            raise AppError("节点编码已存在", code=40031)
        data = payload.model_dump()
        data["company_id"] = company_id
        server = CrawlerServer(**data)
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
        before = {c.name: getattr(server, c.name) for c in server.__table__.columns}
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(server, key, value)
        after = {c.name: getattr(server, c.name) for c in server.__table__.columns}
        write_operation_log(self.db, user, None, operation_type="UPDATE_SERVER", resource_type="server", resource_id=str(server.server_id), before_data=before, after_data=after)
        self.db.commit()
        return server

    def delete_server(self, user: SysUser, server_id: int) -> dict:
        server = self.servers.get(server_id)
        if not server:
            raise AppError("资源不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        require_company_scope(user, server.company_id)
        agent = server.agent
        active_statuses = {"QUEUED", "ROUTED", "ASSIGNED", "STARTING", "RUNNING", "CANCEL_REQUESTED"}
        active_scope = CrawlerTaskRun.server_id == server.server_id
        if agent:
            active_scope = or_(active_scope, CrawlerTaskRun.agent_id == agent.agent_id)
        active_count = int(self.db.scalar(select(func.count()).select_from(CrawlerTaskRun).where(CrawlerTaskRun.run_status.in_(active_statuses), active_scope)) or 0)
        if active_count:
            raise AppError("节点存在运行中任务，不能清理，请等待任务结束后再操作", code=40074, http_status=status.HTTP_400_BAD_REQUEST)

        before = self._server_payload(server)
        agent_id = agent.agent_id if agent else None
        cleanup_counts: dict[str, int] = {}

        def bulk_delete(model, *criteria) -> int:
            count = int(self.db.query(model).filter(*criteria).delete(synchronize_session=False) or 0)
            cleanup_counts[model.__tablename__] = cleanup_counts.get(model.__tablename__, 0) + count
            return count

        bulk_delete(CrawlerProjectServer, CrawlerProjectServer.server_id == server.server_id)
        bulk_delete(CrawlerDiscoveredProjectServer, CrawlerDiscoveredProjectServer.server_id == server.server_id)
        bulk_delete(CrawlerProjectDeploymentTarget, CrawlerProjectDeploymentTarget.server_id == server.server_id)
        bulk_delete(CrawlerOfflineRunSnapshot, CrawlerOfflineRunSnapshot.server_id == server.server_id)

        run_query = self.db.query(CrawlerTaskRun).filter(CrawlerTaskRun.server_id == server.server_id)
        cleanup_counts["crawler_task_run_server_unlinked"] = int(run_query.update({CrawlerTaskRun.server_id: None}, synchronize_session=False) or 0)
        snapshot_query = self.db.query(CrawlerRunContainerSnapshot).filter(CrawlerRunContainerSnapshot.server_id == server.server_id)
        cleanup_counts["crawler_run_container_snapshot_server_unlinked"] = int(snapshot_query.update({CrawlerRunContainerSnapshot.server_id: None}, synchronize_session=False) or 0)
        if agent_id:
            agent_run_query = self.db.query(CrawlerTaskRun).filter(CrawlerTaskRun.agent_id == agent_id)
            cleanup_counts["crawler_task_run_agent_unlinked"] = int(agent_run_query.update({CrawlerTaskRun.agent_id: None}, synchronize_session=False) or 0)
            agent_snapshot_query = self.db.query(CrawlerRunContainerSnapshot).filter(CrawlerRunContainerSnapshot.agent_id == agent_id)
            cleanup_counts["crawler_run_container_snapshot_agent_unlinked"] = int(agent_snapshot_query.update({CrawlerRunContainerSnapshot.agent_id: None}, synchronize_session=False) or 0)
            self.db.delete(agent)
            cleanup_counts["crawler_agent"] = cleanup_counts.get("crawler_agent", 0) + 1

        bulk_delete(CrawlerAgentJoinToken, CrawlerAgentJoinToken.server_code == server.server_code)
        if agent:
            bulk_delete(CrawlerAgentJoinToken, CrawlerAgentJoinToken.agent_code == agent.agent_code)

        self.db.delete(server)
        cleanup_counts["crawler_server"] = cleanup_counts.get("crawler_server", 0) + 1
        write_operation_log(self.db, user, None, operation_type="DELETE_SERVER", resource_type="server", resource_id=str(server_id), before_data=before, after_data={"deleted": True, "cleanupCounts": cleanup_counts})
        self.db.commit()
        return {"server_id": server_id, "deleted": True, "cleanup_counts": cleanup_counts}

    def create_agent_join_token(self, user: SysUser, payload: AgentJoinTokenCreate, detected_base_url: str = "") -> dict:
        company_id = writable_company_id(user, payload.company_id)
        if not self.companies.get(company_id):
            raise AppError("公司不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        exists = self.servers.by_code(payload.server_code)
        if exists and exists.company_id != company_id:
            raise AppError("节点编码已被其他公司使用", code=40032)
        agent = self.agents.by_code(payload.agent_code)
        if agent and agent.company_id != company_id:
            raise AppError("Agent 编码已被其他公司使用", code=40033)
        raw_token = secrets.token_urlsafe(40)
        expires_at = utcnow() + timedelta(hours=payload.expires_in_hours)
        control_plane_url = self._resolve_control_plane_url(payload.control_plane_url, detected_base_url, payload.install_target)
        token = CrawlerAgentJoinToken(
            company_id=company_id,
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
            last_preflight_report={"controlPlaneUrl": control_plane_url},
            created_by=user.user_id,
        )
        self.db.add(token)
        self.db.flush()
        command = self._install_command(raw_token, control_plane_url)
        connectivity_command = f"curl -fsSL {control_plane_url.rstrip('/')}/health && echo"
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
            "connectivityCommand": connectivity_command,
            "controlPlaneUrl": control_plane_url,
            "joinTokenMasked": self._mask_token(raw_token),
            "installTarget": payload.install_target,
            "warnings": [
                *self._control_plane_url_warnings(payload.control_plane_url, control_plane_url, detected_base_url),
                *self._agent_image_warnings(),
            ],
            "note": "该命令包含一次性接入凭证，请只发送给可信运维人员；凭证使用后自动失效。",
        }

    def list_agent_join_tokens(self, user: SysUser, company_id: int | None = None) -> list[dict]:
        scoped = scoped_company_id(user, company_id)
        from sqlalchemy import select
        stmt = select(CrawlerAgentJoinToken).order_by(CrawlerAgentJoinToken.created_at.desc())
        if scoped is not None:
            stmt = stmt.where(CrawlerAgentJoinToken.company_id == scoped)
        rows = list(self.db.scalars(stmt).all())
        return [{**{c.name: getattr(row, c.name) for c in row.__table__.columns}, "tokenHash": "***"} for row in rows]

    def consume_agent_join_token(self, payload: AgentBootstrapEnvRequest, detected_base_url: str = "") -> str:
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
            raise AppError("节点编码已被其他公司使用", code=40032)
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
            raise AppError("节点服务编码已绑定其他节点", code=40033)
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
        previous_report = dict(token.last_preflight_report or {})
        control_plane_url = str(previous_report.get("controlPlaneUrl") or SystemConfigService(self.db).resolve_control_plane_public_base_url(detected_base_url) or "")
        token.last_preflight_report = {**previous_report, **(payload.install_report or {}), "controlPlaneUrl": control_plane_url}
        self.db.commit()
        lines = {
            "AGENT_CONTROL_PLANE_URL": control_plane_url,
            "AGENT_AGENT_TOKEN": raw_agent_token,
            "AGENT_AGENT_CODE": token.agent_code,
            "AGENT_SERVER_CODE": token.server_code,
            "AGENT_MAX_SLOTS": str(token.max_container_slots),
            "AGENT_PROJECT_DATA_ROOT": token.work_dir.rstrip("/") + "/projects",
            "AGENT_RUN_ROOT": token.work_dir.rstrip("/") + "/runs",
            "AGENT_SPOOL_DIR": token.work_dir.rstrip("/") + "/spool",
            "AGENT_IMAGE": settings.crawler_agent_image,
            "AGENT_AGENT_VERSION": settings.crawler_agent_version,
            "AGENT_CAPABILITIES_JSON": __import__('json').dumps(token.capabilities or {}, ensure_ascii=False),
        }
        return "\n".join(f"{k}={self._quote_env(v)}" for k, v in lines.items()) + "\n"

    def _install_command(self, token: str, base: str) -> str:
        public_base = base.rstrip("/")
        return f"curl -fsSL {public_base}/api/v1/agent-installers/linux.sh | bash -s -- --control-plane-url {public_base} --join-token {self._quote_shell(token)}"

    def _resolve_control_plane_url(self, requested_url: str = "", detected_base_url: str = "", install_target: str = "REMOTE") -> str:
        base = (requested_url or SystemConfigService(self.db).resolve_control_plane_public_base_url(detected_base_url) or "").strip().rstrip("/")
        if not base:
            raise AppError("请先填写执行节点可以访问的控制端公网回调地址", code=40071)
        base = self._prefer_detected_origin_port(base, detected_base_url)
        parsed = urlparse(base)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise AppError("控制端公网回调地址必须以 http:// 或 https:// 开头", code=40072)
        host = (parsed.hostname or "").lower()
        if install_target == "REMOTE" and self._is_loopback_host(host):
            raise AppError("远程节点接入不能使用 127.0.0.1 或 localhost，请填写执行节点可访问的控制端公网回调地址", code=40073)
        return base


    @staticmethod
    def _prefer_detected_origin_port(base: str, detected_base_url: str = "") -> str:
        detected_base = (detected_base_url or "").strip().rstrip("/")
        if not detected_base:
            return base
        configured = urlparse(base)
        detected = urlparse(detected_base)
        if configured.scheme not in {"http", "https"} or detected.scheme not in {"http", "https"}:
            return base
        if not configured.hostname or not detected.hostname:
            return base
        same_host = configured.scheme == detected.scheme and configured.hostname.lower() == detected.hostname.lower()
        if not same_host:
            return base
        detected_default_port = 80 if detected.scheme == "http" else 443
        if configured.port is None and detected.port is not None and detected.port != detected_default_port:
            return detected_base
        return base

    def _control_plane_url_warnings(self, requested_url: str, resolved_url: str, detected_base_url: str = "") -> list[str]:
        requested = (requested_url or "").strip().rstrip("/")
        if requested and requested != resolved_url and self._prefer_detected_origin_port(requested, detected_base_url) == resolved_url:
            return [f"配置地址未带端口，已按当前访问入口临时使用 {resolved_url} 生成接入命令；请到系统设置保存完整地址。"]
        return []


    def _agent_image_warnings(self) -> list[str]:
        image = str(settings.crawler_agent_image or "").strip()
        if not image:
            return ["Agent 镜像地址为空，请先配置 CRAWLER_AGENT_IMAGE。"]
        if not self._image_has_registry_prefix(image):
            return [f"Agent 镜像未配置私有仓库前缀：{image}。远程执行节点会默认从 Docker Hub 拉取；生产环境建议配置 CRAWLER_AGENT_IMAGE 为执行节点可访问的私有仓库镜像。"]
        return []

    @staticmethod
    def _image_has_registry_prefix(image: str) -> bool:
        first = (image or "").split("/", 1)[0]
        if not first or first == image:
            return False
        return "." in first or ":" in first or first == "localhost"

    @staticmethod
    def _is_loopback_host(host: str) -> bool:
        return host in {"127.0.0.1", "localhost", "0.0.0.0", "::1"}

    @staticmethod
    def _mask_token(token: str) -> str:
        if len(token) <= 12:
            return "*" * len(token)
        return token[:6] + "********" + token[-6:]

    @staticmethod
    def _quote_shell(value: str) -> str:
        return shlex.quote(str(value or ""))

    @staticmethod
    def _quote_env(value) -> str:
        text = str(value or "")
        return "'" + text.replace("'", "'\\''") + "'"

    def register_agent(self, user: SysUser, payload: AgentRegistration) -> dict:
        company_id = writable_company_id(user, payload.company_id)
        if not self.companies.get(company_id):
            raise AppError("公司不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        server = self.servers.by_code(payload.server_code)
        if not server:
            server = CrawlerServer(
                company_id=company_id,
                server_code=payload.server_code,
                server_name=payload.server_name,
                server_ip=payload.server_ip,
                max_container_slots=payload.max_container_slots,
                manage_status="ENABLED",
            )
            self.servers.add(server)
        elif server.company_id != company_id:
            raise AppError("节点编码已被其他公司使用", code=40032)
        agent = self.agents.by_code(payload.agent_code)
        if agent and agent.server_id != server.server_id:
            raise AppError("节点服务编码已绑定其他节点", code=40033)
        raw_token = secrets.token_urlsafe(36)
        if not agent:
            agent = CrawlerAgent(
                company_id=company_id,
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
        write_operation_log(self.db, user, None, operation_type="REGISTER_AGENT", resource_type="agent", resource_id=str(agent.agent_id), after_data={"agentId": agent.agent_id, "agentCode": agent.agent_code, "serverId": server.server_id, "companyId": company_id})
        self.db.commit()
        return {"agent": {"agentId": agent.agent_id, "agentCode": agent.agent_code, "agentName": agent.agent_name, "connectionStatus": agent.connection_status, "serverId": agent.server_id}, "server": server, "agentToken": raw_token}

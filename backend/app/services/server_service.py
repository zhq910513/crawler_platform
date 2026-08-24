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
from app.schemas import AgentBootstrapEnvRequest, AgentBootstrapFailureReport, AgentJoinTokenCreate, AgentRegistration, ServerCreate, ServerUpdate
from app.security import hash_password
from app.services.permissions import require_company_scope, scoped_company_id, writable_company_id
from app.services.audit import write_operation_log
from app.config import settings
from app.services.system_config_service import SystemConfigService
from app.services.agent_command_service import AgentCommandService
from app.services.alert_service import AlertService
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
        before = self._server_payload(server)
        agent = server.agent
        active_statuses = {"QUEUED", "ROUTED", "ASSIGNED", "STARTING", "RUNNING", "CANCEL_REQUESTED"}
        active_scope = CrawlerTaskRun.server_id == server.server_id
        if agent:
            active_scope = or_(active_scope, CrawlerTaskRun.agent_id == agent.agent_id)
        active_count = int(self.db.scalar(select(func.count()).select_from(CrawlerTaskRun).where(CrawlerTaskRun.run_status.in_(active_statuses), active_scope)) or 0)
        if active_count:
            # Desired State：用户发起移除后，平台先进入 Drain，不再把“等待任务结束”交给人工二次点击。
            server.previous_manage_status = server.manage_status or server.previous_manage_status or "ENABLED"
            server.manage_status = "MAINTENANCE"
            server.desired_state = "DECOMMISSIONED"
            server.lifecycle_status = "DRAINING"
            server.lifecycle_action = "DECOMMISSION"
            server.lifecycle_error = ""
            server.lifecycle_started_at = utcnow()
            write_operation_log(
                self.db, user, None, operation_type="DECOMMISSION_SERVER_DRAINING", resource_type="server",
                resource_id=str(server_id), before_data=before,
                after_data={"deleted": False, "decommissioning": True, "activeRuns": active_count},
            )
            self.db.commit()
            return {
                "server_id": server_id,
                "deleted": False,
                "decommissioning": True,
                "draining": True,
                "active_runs": active_count,
                "message": "已进入维护/Drain 状态，不再接收新任务；运行任务结束后平台会自动继续退役。",
            }

        # 在线节点优先通过现有心跳指令通道退役，避免平台记录删除后远端 crawler-agent
        # 仍以 restart=always 持续运行并反复使用已失效 Token。
        offline_before = utcnow() - timedelta(seconds=max(30, settings.agent_lease_seconds * 2))
        supports_decommission = bool(agent and isinstance(agent.capabilities, dict) and agent.capabilities.get("agentDecommission") is True)
        if agent and supports_decommission and agent.connection_status == "ONLINE" and agent.last_heartbeat_at and agent.last_heartbeat_at >= offline_before:
            server.manage_status = "DISABLED"
            server.desired_state = "DECOMMISSIONED"
            server.lifecycle_status = "DECOMMISSIONING"
            server.lifecycle_action = "DECOMMISSION"
            server.lifecycle_error = ""
            server.lifecycle_started_at = utcnow()
            metrics = dict(server.metrics or {})
            if not any(isinstance(item, dict) and item.get("commandType") == "AGENT_DECOMMISSION" and item.get("status") == "PENDING" for item in metrics.get("pendingAgentCommands", []) or []):
                AgentCommandService(self.db).enqueue_agent_decommission(server=server, agent_id=agent.agent_id)
            metrics = dict(server.metrics or {})
            metrics["decommissionStatus"] = "PENDING"
            metrics["decommissionRequestedAt"] = utcnow().isoformat()
            server.metrics = metrics
            write_operation_log(
                self.db, user, None, operation_type="DECOMMISSION_SERVER_REQUESTED", resource_type="server",
                resource_id=str(server_id), before_data=before,
                after_data={"deleted": False, "decommissioning": True, "agentCode": agent.agent_code},
            )
            self.db.commit()
            return {
                "server_id": server_id,
                "deleted": False,
                "decommissioning": True,
                "cleanup_counts": {},
                "message": "已停止节点接收新任务并下发远端 Agent 退役指令；Agent 确认后平台会自动删除节点和接入记录。",
                "manual_cleanup_command": self._agent_local_cleanup_command(),
            }

        live_but_legacy = bool(agent and not supports_decommission and agent.connection_status == "ONLINE" and agent.last_heartbeat_at and agent.last_heartbeat_at >= offline_before)
        cleanup_counts = self._delete_server_records(server, agent)
        cleanup_command = self._agent_local_cleanup_command()
        if agent and (live_but_legacy or not supports_decommission):
            AlertService(self.db).raise_event(
                severity="P1",
                alert_type="AGENT_REMOTE_CLEANUP_UNCONFIRMED",
                title="远端 Agent 清理未确认",
                content=f"节点 {before.get('server_name') or before.get('server_code') or server_id} 已从平台移除并撤销凭据，但平台无法确认远端 crawler-agent 容器已停止。请在目标服务器执行：{cleanup_command}",
                fingerprint=f"agent-remote-cleanup:{server.company_id}:{server_id}",
                company_id=server.company_id,
            )
        write_operation_log(
            self.db, user, None, operation_type="DELETE_SERVER", resource_type="server", resource_id=str(server_id),
            before_data=before,
            after_data={"deleted": True, "cleanupCounts": cleanup_counts, "remoteAgentReachable": live_but_legacy, "remoteAutoDecommissionSupported": supports_decommission, "manualCleanupCommand": cleanup_command},
        )
        self.db.commit()
        message = (
            "平台节点和接入记录已清理；当前 Agent 未声明自动退役能力，旧 Token 已失效。请在目标服务器执行返回的清理命令移除旧 Agent 容器和失效凭证。"
            if live_but_legacy
            else "平台节点和接入记录已清理；该节点当前不在线，无法确认远端容器是否仍存在。旧 Agent Token 已失效。"
        )
        return {
            "server_id": server_id,
            "deleted": True,
            "decommissioning": False,
            "cleanup_counts": cleanup_counts,
            "message": message,
            "manual_cleanup_command": cleanup_command,
        }

    def _delete_server_records(self, server: CrawlerServer, agent: CrawlerAgent | None) -> dict[str, int]:
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
        return cleanup_counts


    def finalize_agent_decommission_unconfirmed(self, server: CrawlerServer, agent: CrawlerAgent | None, reason: str = "") -> dict:
        before = self._server_payload(server)
        server_id = server.server_id
        cleanup_command = self._agent_local_cleanup_command()
        cleanup_counts = self._delete_server_records(server, agent)
        AlertService(self.db).raise_event(
            severity="P1",
            alert_type="AGENT_REMOTE_CLEANUP_UNCONFIRMED",
            title="远端 Agent 清理未确认",
            content=f"节点 {before.get('server_name') or before.get('server_code') or server_id} 已从平台移除并撤销凭据，但平台无法确认远端 crawler-agent 容器已停止。原因：{reason or 'Agent 不在线或不支持自动退役'}。请在目标服务器执行：{cleanup_command}",
            fingerprint=f"agent-remote-cleanup:{before.get('company_id')}:{server_id}",
            company_id=before.get('company_id'),
        )
        write_operation_log(
            self.db, None, None, operation_type="DECOMMISSION_SERVER_UNCONFIRMED", resource_type="server", resource_id=str(server_id),
            before_data=before, after_data={"deleted": True, "cleanupCounts": cleanup_counts, "remoteAgentCleanupUnconfirmed": True, "reason": reason, "manualCleanupCommand": cleanup_command},
        )
        return {"deleted": True, "cleanup_counts": cleanup_counts, "manual_cleanup_command": cleanup_command}

    def finalize_agent_decommission(self, agent: CrawlerAgent) -> dict:
        server = self.db.get(CrawlerServer, agent.server_id)
        if not server:
            return {"deleted": True, "cleanup_counts": {}}
        before = self._server_payload(server)
        server_id = server.server_id
        cleanup_counts = self._delete_server_records(server, agent)
        write_operation_log(
            self.db, None, None, operation_type="DECOMMISSION_SERVER_COMPLETED", resource_type="server", resource_id=str(server_id),
            before_data=before, after_data={"deleted": True, "cleanupCounts": cleanup_counts, "remoteAgentDecommissioned": True},
        )
        return {"deleted": True, "cleanup_counts": cleanup_counts}

    @staticmethod
    def _agent_local_cleanup_command() -> str:
        # 不删除 /data/crawler-agent 等业务数据目录；只移除平台安装的 Agent 容器和失效凭证。
        return "docker rm -f crawler-agent 2>/dev/null || true; rm -f /opt/crawler-agent/.env"

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
        if agent and agent.connection_status == "ONLINE":
            raise AppError("该执行节点 Agent 当前在线；在线节点不应重新生成 Join Token，请使用维护、升级或移除流程。", code=40077, http_status=status.HTTP_400_BAD_REQUEST)
        self._assert_agent_runtime_target_consistent()
        raw_token = secrets.token_urlsafe(40)
        expires_at = utcnow() + timedelta(hours=payload.expires_in_hours)
        control_plane_url = self._resolve_control_plane_url(payload.control_plane_url, detected_base_url, payload.install_target)
        control_preflight = SystemConfigService(self.db).inspect_control_plane_preflight(control_plane_url, detected_base_url)
        if payload.install_target == "REMOTE" and not control_preflight.get("readyForRemoteAgent"):
            blockers = [item for item in control_preflight.get("checks", []) if item.get("blocking") and item.get("status") == "FAIL"]
            detail = "；".join(f"{item.get('label')}: {item.get('message')}" for item in blockers[:3])
            message = control_preflight.get("summary") or "控制端接入预检未通过"
            if detail:
                message = f"{message}：{detail}"
            raise AppError(message, code=40075, http_status=status.HTTP_400_BAD_REQUEST)
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
        command = self._install_command(raw_token, control_plane_url, payload.replace_existing_agent, payload.auto_configure_docker_registry, "replace_existing_agent" in payload.model_fields_set)
        connectivity_command = f"curl -fsS --connect-timeout 3 --max-time 10 {control_plane_url.rstrip('/')}/health && echo"
        node_verification_script = self._node_verification_script(control_plane_url)
        write_operation_log(self.db, user, None, operation_type="CREATE_AGENT_JOIN_TOKEN", resource_type="agent", resource_id=str(token.token_id), after_data={"tokenId": token.token_id, "companyId": token.company_id, "agentCode": token.agent_code, "serverCode": token.server_code})
        self.db.commit()
        return {
            "tokenId": token.token_id,
            "companyId": token.company_id,
            "invitationStatus": token.invitation_status,
            "invitationStatusLabel": self._invitation_status_label(token.invitation_status),
            "agentCode": token.agent_code,
            "serverCode": token.server_code,
            "expiresAt": token.expires_at,
            "joinToken": raw_token,
            "installCommand": command,
            "connectivityCommand": connectivity_command,
            "nodeVerificationScript": node_verification_script,
            "controlPlaneUrl": control_plane_url,
            "joinTokenMasked": self._mask_token(raw_token),
            "installTarget": payload.install_target,
            "warnings": [
                *self._control_plane_url_warnings(payload.control_plane_url, control_plane_url, detected_base_url),
                *self._agent_image_warnings(),
                ("默认启用智能替换：已有 Agent 无任务时可回滚替换，有任务时会在消耗 Join Token 前停止并提示等待。" if payload.replace_existing_agent else "已选择保守模式：发现已有 Agent 会在消耗 Join Token 前停止。"),
                ("已明确授权安装脚本在 Registry 网络验证通过后配置 Docker HTTP 私有仓库；该动作会备份 daemon.json 并重启 Docker。" if payload.auto_configure_docker_registry else "默认不会修改 Docker daemon.json 或重启 Docker；如检测到 HTTP 私有仓库尚未配置，脚本会在消耗接入凭证前停止。"),
            ],
            "controlPlanePreflight": control_preflight,
            "note": "该命令包含一次性接入凭证，请只发送给可信运维人员；凭证使用后自动失效。",
        }

    def list_agent_join_tokens(self, user: SysUser, company_id: int | None = None) -> list[dict]:
        scoped = scoped_company_id(user, company_id)
        self._mark_stale_config_issued_join_tokens(scoped)
        from sqlalchemy import select
        stmt = select(CrawlerAgentJoinToken).order_by(CrawlerAgentJoinToken.created_at.desc())
        if scoped is not None:
            stmt = stmt.where(CrawlerAgentJoinToken.company_id == scoped)
        stmt = stmt.where(CrawlerAgentJoinToken.invitation_status.in_(["PENDING", "CONFIG_ISSUED", "FAILED"]))
        rows = list(self.db.scalars(stmt).all())
        return [{**{c.name: getattr(row, c.name) for c in row.__table__.columns}, "tokenHash": "***"} for row in rows]

    def _mark_stale_config_issued_join_tokens(self, company_id: int | None = None) -> None:
        now = utcnow()
        cutoff = now - timedelta(minutes=5)
        stmt = select(CrawlerAgentJoinToken).where(
            CrawlerAgentJoinToken.status == "USED",
            CrawlerAgentJoinToken.invitation_status == "CONFIG_ISSUED",
            CrawlerAgentJoinToken.used_at.is_not(None),
            CrawlerAgentJoinToken.used_at < cutoff,
        )
        if company_id is not None:
            stmt = stmt.where(CrawlerAgentJoinToken.company_id == company_id)
        changed = False
        for token in self.db.scalars(stmt).all():
            token.invitation_status = "FAILED"
            token.failed_at = token.failed_at or now
            token.failure_stage = "FIRST_HEARTBEAT_TIMEOUT"
            token.failure_reason = token.failure_reason or "已下发 Agent 配置但超过 5 分钟未收到首轮心跳；请查看目标机 docker logs --tail 200 crawler-agent。"
            changed = True
        if changed:
            self.db.commit()

    def delete_agent_join_token(self, user: SysUser, token_id: int) -> dict:
        token = self.db.get(CrawlerAgentJoinToken, token_id)
        if not token:
            raise AppError("接入记录不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        require_company_scope(user, token.company_id)
        server = self.servers.by_code(token.server_code)
        if server:
            raise AppError("该接入记录已生成节点，请从执行节点列表清理节点；节点清理会同步删除接入记录", code=40076, http_status=status.HTTP_400_BAD_REQUEST)
        before = {c.name: getattr(token, c.name) for c in token.__table__.columns}
        self.db.delete(token)
        write_operation_log(self.db, user, None, operation_type="DELETE_AGENT_JOIN_TOKEN", resource_type="agent_join_token", resource_id=str(token_id), before_data=before, after_data={"deleted": True})
        self.db.commit()
        return {"token_id": token_id, "deleted": True}


    def precheck_agent_join_token(self, join_token: str) -> dict:
        self._assert_agent_runtime_target_consistent()
        token = self.db.scalar(select(CrawlerAgentJoinToken).where(CrawlerAgentJoinToken.token_hash == sha256_text(join_token), CrawlerAgentJoinToken.status == "ACTIVE"))
        if not token:
            raise AppError("Agent 接入令牌无效或已使用", code=40160, http_status=status.HTTP_401_UNAUTHORIZED)
        if token.expires_at and token.expires_at < utcnow():
            token.status = "EXPIRED"
            self.db.commit()
            raise AppError("Agent 接入令牌已过期", code=40161, http_status=status.HTTP_401_UNAUTHORIZED)
        return {"accepted": True, "invitationStatus": token.invitation_status, "tokenId": token.token_id}

    def report_agent_join_failure(self, payload: AgentBootstrapFailureReport) -> dict:
        token = self.db.scalar(select(CrawlerAgentJoinToken).where(CrawlerAgentJoinToken.token_hash == sha256_text(payload.join_token)))
        if not token:
            # 安装脚本失败上报不应泄漏 token 是否存在，返回 accepted=false 便于脚本继续显示本地错误。
            return {"accepted": False, "message": "接入邀请未找到或已失效"}
        token.invitation_status = "FAILED"
        token.failure_stage = (payload.failure_stage or "UNKNOWN")[:120]
        token.failure_reason = (payload.failure_reason or "")[:1000]
        token.failed_at = utcnow()
        previous_report = dict(token.last_preflight_report or {})
        token.last_preflight_report = {**previous_report, **(payload.install_report or {}), "failureStage": token.failure_stage, "failureReason": token.failure_reason}
        self.db.commit()
        return {"accepted": True, "invitationStatus": token.invitation_status, "failureStage": token.failure_stage}


    def resume_agent_bootstrap_env(self, agent: CrawlerAgent, detected_base_url: str = "", join_token: str = "") -> str:
        self._assert_agent_runtime_target_consistent()
        server = self.db.get(CrawlerServer, agent.server_id)
        if not server:
            raise AppError("执行节点绑定关系不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        if server.desired_state == "DECOMMISSIONED" or server.lifecycle_action == "DECOMMISSION":
            raise AppError("该节点正在退役，不能复用旧 Agent 凭据续跑安装", code=40931, http_status=status.HTTP_409_CONFLICT)
        if join_token:
            token = self.db.scalar(select(CrawlerAgentJoinToken).where(CrawlerAgentJoinToken.token_hash == sha256_text(join_token)).order_by(CrawlerAgentJoinToken.created_at.desc()).limit(1))
            if not token:
                raise AppError("当前接入命令无法匹配本机长期 Agent 凭据，请使用 Join Token 重新接入。", code=40932, http_status=status.HTTP_409_CONFLICT)
            if token.agent_code != agent.agent_code or token.server_code != server.server_code:
                raise AppError("本机长期 Agent 凭据不属于当前接入命令，不能跳过 Join Token；将使用本次 Join Token 重新接入。", code=40933, http_status=status.HTTP_409_CONFLICT)
        control_plane_url = SystemConfigService(self.db).resolve_control_plane_public_base_url(detected_base_url) or detected_base_url.rstrip("/")
        server.desired_agent_version = settings.crawler_agent_version
        if server.lifecycle_status in {"BOOTSTRAPPING", "INSTALLING"}:
            server.lifecycle_error = ""
        self.db.commit()
        work_dir = (server.work_dir or "/data/crawler-agent").rstrip("/")
        capabilities = agent.capabilities or server.capabilities or {}
        lines = {
            "AGENT_CONTROL_PLANE_URL": control_plane_url,
            "AGENT_AGENT_CODE": agent.agent_code,
            "AGENT_SERVER_CODE": server.server_code,
            "AGENT_MAX_SLOTS": str(server.max_container_slots),
            "AGENT_PROJECT_DATA_ROOT": work_dir + "/projects",
            "AGENT_RUN_ROOT": work_dir + "/runs",
            "AGENT_SPOOL_DIR": work_dir + "/spool",
            "AGENT_IMAGE": settings.crawler_agent_image,
            "AGENT_EXPECTED_IMAGE_DIGEST": settings.crawler_agent_image_digest,
            "AGENT_AGENT_VERSION": settings.crawler_agent_version,
            "AGENT_CAPABILITIES_JSON": __import__('json').dumps(capabilities, ensure_ascii=False),
        }
        return "\n".join(f"{k}={self._quote_env(v)}" for k, v in lines.items()) + "\n"

    def consume_agent_join_token(self, payload: AgentBootstrapEnvRequest, detected_base_url: str = "") -> str:
        from sqlalchemy import select
        self._assert_agent_runtime_target_consistent()
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
                desired_state="ONLINE",
                desired_agent_version=settings.crawler_agent_version,
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
        server.desired_state = "ONLINE"
        server.desired_agent_version = settings.crawler_agent_version
        server.lifecycle_status = "BOOTSTRAPPING"
        server.lifecycle_action = "JOIN"
        server.lifecycle_error = ""
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
        token.invitation_status = "CONFIG_ISSUED"
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
            "AGENT_EXPECTED_IMAGE_DIGEST": settings.crawler_agent_image_digest,
            "AGENT_AGENT_VERSION": settings.crawler_agent_version,
            "AGENT_CAPABILITIES_JSON": __import__('json').dumps(token.capabilities or {}, ensure_ascii=False),
        }
        return "\n".join(f"{k}={self._quote_env(v)}" for k, v in lines.items()) + "\n"

    @staticmethod
    def _invitation_status_label(status: str) -> str:
        return {
            "PENDING": "待接入",
            "CONFIG_ISSUED": "接入中",
            "ACTIVATED": "已接入",
            "FAILED": "接入失败",
            "EXPIRED": "已过期",
            "CANCELLED": "已取消",
        }.get(status or "", status or "未知")

    def _node_verification_script(self, control_plane_url: str) -> str:
        base = control_plane_url.rstrip('/')
        lines = [
            "set -Eeuo pipefail",
            f"curl -fsS --connect-timeout 3 --max-time 10 {base}/health && echo",
            "tmp_installer=\"$(mktemp)\"",
            f"curl -fsS --connect-timeout 3 --max-time 10 {base}/api/v1/agent-installers/linux.sh -o \"$tmp_installer\"",
            "head -5 \"$tmp_installer\"",
            "rm -f \"$tmp_installer\"",
        ]
        image = str(settings.crawler_agent_image or "").strip()
        if image and self._image_has_registry_prefix(image):
            registry = image.split('/', 1)[0]
            host = registry.rsplit(':', 1)[0] if ':' in registry else registry
            port = int(registry.rsplit(':', 1)[1]) if ':' in registry and registry.rsplit(':', 1)[1].isdigit() else 443
            scheme = "http" if port in {5000, 80} or host in {"localhost", "127.0.0.1"} else "https"
            lines.extend([
                f"curl -fsS --connect-timeout 3 --max-time 10 {scheme}://{registry}/v2/ && echo",
                f"docker pull {shlex.quote(image)}",
            ])
        else:
            lines.append("echo '执行组件镜像地址尚未配置私有仓库前缀，请先查看运行总览平台自检。'")
        return "\n".join(lines)

    @staticmethod
    def _agent_image_tag(image: str) -> str:
        value = str(image or "").strip()
        if not value:
            return ""
        last = value.rsplit("/", 1)[-1]
        if ":" not in last:
            return ""
        return last.rsplit(":", 1)[-1].strip()

    def _assert_agent_runtime_target_consistent(self) -> None:
        image = str(settings.crawler_agent_image or "").strip()
        version = str(settings.crawler_agent_version or "").strip()
        if not image:
            raise AppError("执行组件镜像地址为空，请先准备 Agent 镜像。", code=40082, http_status=status.HTTP_400_BAD_REQUEST)
        if not version:
            raise AppError("Agent 目标版本为空，请先配置 AGENT_AGENT_VERSION。", code=40083, http_status=status.HTTP_400_BAD_REQUEST)
        tag = self._agent_image_tag(image)
        if not tag:
            raise AppError(f"执行组件镜像必须带明确 tag，当前为：{image}", code=40084, http_status=status.HTTP_400_BAD_REQUEST)
        if tag != version:
            raise AppError(
                f"Agent 运行目标未准备完成：AGENT_AGENT_VERSION={version}，但 CRAWLER_AGENT_IMAGE={image}。请先执行 prepare-agent-image.sh 准备并写入 {version} 镜像。",
                code=40085,
                http_status=status.HTTP_400_BAD_REQUEST,
            )

    @staticmethod
    def _image_has_registry_prefix(image: str) -> bool:
        first = (image or "").split("/", 1)[0]
        if not first or first == image:
            return False
        return "." in first or ":" in first or first == "localhost"

    def _install_command(self, token: str, base: str, replace_existing_agent: bool = True, auto_configure_docker_registry: bool = False, explicit_replace_flag: bool = False) -> str:
        public_base = base.rstrip("/")
        flags: list[str] = []
        if auto_configure_docker_registry:
            flags.append("--auto-configure-docker-registry")
        if replace_existing_agent and explicit_replace_flag:
            flags.append("--replace-existing-agent")
        elif not replace_existing_agent:
            flags.append("--no-replace-existing-agent")
        suffix = (" " + " ".join(flags)) if flags else ""
        quoted_base = self._quote_shell(public_base)
        quoted_token = self._quote_shell(token)
        return "\n".join([
            "set -Eeuo pipefail",
            "tmp_installer=\"$(mktemp)\"",
            f"curl -fsS --connect-timeout 3 --max-time 15 {quoted_base}/api/v1/agent-installers/linux.sh -o \"$tmp_installer\"",
            "set +e",
            f"bash \"$tmp_installer\" --control-plane-url {quoted_base} --join-token {quoted_token}{suffix}",
            "rc=$?",
            "set -e",
            "rm -f \"$tmp_installer\"",
            "if [ \"$rc\" -eq 0 ]; then",
            "  echo \"Agent 安装脚本执行完成，退出码：0。控制台会自动刷新首轮心跳状态。\"",
            "else",
            "  echo \"Agent 安装脚本已结束，退出码：$rc。当前 SSH 会话不会退出，请根据上方错误处理后重试。\" >&2",
            "fi",
        ])

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
            return ["执行组件镜像地址为空，请先配置 CRAWLER_AGENT_IMAGE。"]
        if not self._image_has_registry_prefix(image):
            return [f"执行组件镜像未配置私有仓库前缀：{image}。远程执行节点会默认从 Docker Hub 拉取；生产环境建议配置 CRAWLER_AGENT_IMAGE 为执行节点可访问的私有仓库镜像。"]
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

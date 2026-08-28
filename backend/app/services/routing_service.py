from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CrawlerAgent, CrawlerProject, CrawlerProjectServer, CrawlerServer, CrawlerTask, CrawlerTaskRun, CrawlerTaskServerTarget
from app.services.state_machine import set_routing_status


@dataclass
class Candidate:
    server: CrawlerServer
    project_server: CrawlerProjectServer | None
    layer: str
    priority: int
    weight: int
    max_concurrency: int


class RoutingService:
    def __init__(self, db: Session):
        self.db = db

    def route_run(self, run: CrawlerTaskRun) -> CrawlerTaskRun:
        task = self.db.get(CrawlerTask, run.task_id)
        project = self.db.get(CrawlerProject, run.project_id)
        if not task or not project:
            run.server_id = None
            set_routing_status(run, "ROUTE_FAILED", reason="任务或项目不存在")
            return run
        limit_reason = self._runtime_policy_block_reason(run, task)
        if limit_reason:
            run.server_id = None
            set_routing_status(run, "WAITING_RESOURCE", reason=limit_reason)
            return run
        candidates = self._resolve_candidates(task, project, run.release_id)
        if not candidates:
            run.server_id = None
            set_routing_status(run, "WAITING_RESOURCE", reason="暂无可用执行节点或镜像未就绪")
            return run
        available = self._score_candidates(candidates)
        if not available:
            run.server_id = None
            set_routing_status(run, "WAITING_RESOURCE", reason="候选执行节点资源不足")
            return run
        candidate = available[0][1]
        run.server_id = candidate.server.server_id
        if candidate.project_server and candidate.project_server.image_readiness_status in {"OUTDATED", "WARMING"}:
            candidate.project_server.image_readiness_status = "WARMING"
            set_routing_status(run, "WARMING_IMAGE", reason=f"已通过{candidate.layer}选中执行节点，节点服务将按 digest 预热镜像")
            # 当前 Agent 在领取时会先精确拉取 digest，因此可立即转为可领取状态。
            set_routing_status(run, "ROUTED", reason=f"已通过{candidate.layer}分配到可用执行节点，镜像将在运行前校验")
        else:
            set_routing_status(run, "ROUTED", reason=f"已通过{candidate.layer}分配到可用执行节点")
        return run

    def reroute_or_wait_unclaimed(self, commit: bool = True) -> int:
        runs = list(self.db.scalars(select(CrawlerTaskRun).where(CrawlerTaskRun.run_status == "QUEUED", CrawlerTaskRun.routing_status.in_(["PENDING", "WAITING_RESOURCE", "WARMING_IMAGE", "ROUTED"])).limit(300)).all())
        count = 0
        for run in runs:
            if (run.routing_reason or "").startswith("重叠策略排队") and self._has_older_active_run(run):
                continue
            if (run.routing_reason or "").startswith("重叠策略排队"):
                run.server_id = None
                set_routing_status(run, "PENDING", reason="上一轮已结束，释放排队运行实例")
            if run.routing_status == "ROUTED" and run.server_id and self._server_still_eligible(run):
                continue
            if run.routing_status == "ROUTED":
                run.server_id = None
                set_routing_status(run, "PENDING", reason="目标节点不可用，重新分配")
            self.route_run(run)
            count += 1
        if commit:
            self.db.commit()
        return count

    def _has_older_active_run(self, run: CrawlerTaskRun) -> bool:
        active = self.db.scalar(select(func.count(CrawlerTaskRun.run_id)).where(CrawlerTaskRun.task_id == run.task_id, CrawlerTaskRun.run_id != run.run_id, CrawlerTaskRun.root_run_id != run.root_run_id, CrawlerTaskRun.run_status.in_(["QUEUED", "ASSIGNED", "STARTING", "RUNNING", "CANCEL_REQUESTED"]))) or 0
        return active > 0

    def _server_still_eligible(self, run: CrawlerTaskRun) -> bool:
        if not run.server_id:
            return False
        task = self.db.get(CrawlerTask, run.task_id)
        project = self.db.get(CrawlerProject, run.project_id)
        if not task or not project:
            return False
        return any(c.server.server_id == run.server_id for c in self._resolve_candidates(task, project, run.release_id))

    def _runtime_policy_block_reason(self, run: CrawlerTaskRun, task: CrawlerTask) -> str:
        active_statuses = ["QUEUED", "ASSIGNED", "STARTING", "RUNNING", "CANCEL_REQUESTED"]
        # 任务级并发：包括已分配和运行中的同一任务实例，排除当前 run。
        task_active = self.db.scalar(select(func.count(CrawlerTaskRun.run_id)).where(
            CrawlerTaskRun.task_id == task.task_id,
            CrawlerTaskRun.run_id != run.run_id,
            CrawlerTaskRun.run_status.in_(active_statuses),
            CrawlerTaskRun.routing_status != "ROUTE_CANCELLED",
        )) or 0
        if task.task_max_concurrency and task_active >= task.task_max_concurrency:
            return f"任务级并发已满：当前 {task_active}/{task.task_max_concurrency}"
        # 任务组并发：同项目、同任务组共享限流，适合浏览器组、下载组、登录组。
        group = task.task_group or "default"
        group_limit = task.group_max_concurrency or 1
        group_active = self.db.scalar(select(func.count(CrawlerTaskRun.run_id)).where(
            CrawlerTaskRun.project_id == task.project_id,
            CrawlerTaskRun.task_group == group,
            CrawlerTaskRun.run_id != run.run_id,
            CrawlerTaskRun.run_status.in_(active_statuses),
            CrawlerTaskRun.routing_status != "ROUTE_CANCELLED",
        )) or 0
        if group_active >= group_limit:
            return f"任务组并发已满：{group} 当前 {group_active}/{group_limit}"
        # 独占任务：适合登录态维护、高 IO、高风险操作。该任务运行时项目内不再释放其他新运行。
        if task.exclusive_mode:
            project_active = self.db.scalar(select(func.count(CrawlerTaskRun.run_id)).where(
                CrawlerTaskRun.project_id == task.project_id,
                CrawlerTaskRun.run_id != run.run_id,
                CrawlerTaskRun.run_status.in_(active_statuses),
                CrawlerTaskRun.routing_status != "ROUTE_CANCELLED",
            )) or 0
            if project_active > 0:
                return f"任务要求独占运行，当前项目仍有 {project_active} 个活动运行实例"
        # 资源锁：账号、Profile、代理、站点限流等可通过 resourceLocks 声明。
        locks = set(str(item) for item in (task.resource_locks or []) if str(item).strip())
        if locks:
            rows = self.db.scalars(select(CrawlerTaskRun).where(
                CrawlerTaskRun.project_id == task.project_id,
                CrawlerTaskRun.run_id != run.run_id,
                CrawlerTaskRun.run_status.in_(active_statuses),
                CrawlerTaskRun.routing_status != "ROUTE_CANCELLED",
            ).limit(500)).all()
            for active in rows:
                active_locks = set(str(item) for item in (active.resource_locks or []) if str(item).strip())
                conflict = locks & active_locks
                if conflict:
                    return f"资源锁被占用：{', '.join(sorted(conflict))}"
        return ""

    def _resolve_candidates(self, task: CrawlerTask, project: CrawlerProject, release_id: int | None) -> list[Candidate]:
        target_ids = list(self.db.scalars(select(CrawlerTaskServerTarget.server_id).where(CrawlerTaskServerTarget.task_id == task.task_id, CrawlerTaskServerTarget.enabled.is_(True))).all())
        if target_ids:
            # Explicit task targets are a routing constraint, not a soft preference.
            # Falling back to another project/company node would violate the operator's
            # placement decision and can also bypass node-local network/credential assumptions.
            return self._project_pool_candidates(task, project, release_id, layer="任务指定节点", server_ids=set(target_ids), include_candidate=True)
        candidates = self._project_pool_candidates(task, project, release_id, layer="项目执行节点范围", enabled_only=True)
        if candidates:
            return candidates
        if project.allow_deployed_fallback:
            candidates = self._project_pool_candidates(task, project, release_id, layer="项目已部署节点兜底", include_candidate=True, allow_paused=False)
            if candidates:
                return candidates
        if project.allow_company_pool_fallback:
            return self._company_pool_candidates(task, project.company_id)
        return []

    def _project_pool_candidates(self, task: CrawlerTask, project: CrawlerProject, release_id: int | None, layer: str, server_ids: set[int] | None = None, enabled_only: bool = False, include_candidate: bool = False, allow_paused: bool = False) -> list[Candidate]:
        role_filter = ["ACTIVE", "PRIMARY", "STANDBY"] if not include_candidate else ["ACTIVE", "PRIMARY", "STANDBY", "CANDIDATE"]
        status_filter = ["ENABLED", "RECOVERING"] if enabled_only or not allow_paused else ["ENABLED", "RECOVERING", "PAUSED"]
        stmt = select(CrawlerServer, CrawlerProjectServer).join(CrawlerProjectServer, CrawlerProjectServer.server_id == CrawlerServer.server_id).join(CrawlerAgent, CrawlerAgent.server_id == CrawlerServer.server_id).where(
            CrawlerProjectServer.project_id == project.project_id,
            CrawlerProjectServer.deployment_status == "DEPLOYED",
            CrawlerProjectServer.latest_release_id == release_id,
            CrawlerProjectServer.scheduling_status.in_(status_filter),
            CrawlerProjectServer.image_readiness_status == "READY",
            CrawlerProjectServer.server_role.in_(role_filter),
            CrawlerServer.manage_status == "ENABLED",
            CrawlerServer.health_status.in_(["HEALTHY", "DEGRADED"]),
            CrawlerServer.capacity_status.in_(["NORMAL", "PRESSURE"]),
            CrawlerAgent.connection_status == "ONLINE",
        )
        if server_ids:
            stmt = stmt.where(CrawlerServer.server_id.in_(server_ids))
        rows = [(s, ps) for s, ps in self.db.execute(stmt).all() if self._capabilities_match(getattr(s, "agent", None).capabilities if getattr(s, "agent", None) else {}, task.required_capabilities or {})]
        if project.dispatch_mode == "PRIMARY_STANDBY":
            primary = [(s, ps) for s, ps in rows if ps.server_role == "PRIMARY"]
            if primary:
                rows = primary
            else:
                rows = [(s, ps) for s, ps in rows if ps.server_role == "STANDBY"]
        else:
            rows = [(s, ps) for s, ps in rows if ps.server_role in {"ACTIVE", "CANDIDATE"}]
        if project.max_active_servers and len(rows) > project.max_active_servers:
            rows = sorted(rows, key=lambda row: (row[1].priority, -row[1].weight))[:project.max_active_servers]
        return [Candidate(server=s, project_server=ps, layer=layer, priority=ps.priority, weight=ps.weight, max_concurrency=ps.max_concurrency) for s, ps in rows]

    def _company_pool_candidates(self, task: CrawlerTask, company_id: int) -> list[Candidate]:
        stmt = select(CrawlerServer).join(CrawlerAgent, CrawlerAgent.server_id == CrawlerServer.server_id).where(CrawlerServer.company_id == company_id, CrawlerServer.manage_status == "ENABLED", CrawlerServer.health_status.in_(["HEALTHY", "DEGRADED"]), CrawlerServer.capacity_status.in_(["NORMAL", "PRESSURE"]), CrawlerAgent.connection_status == "ONLINE")
        rows = [s for s in self.db.scalars(stmt).all() if self._capabilities_match(s.agent.capabilities if s.agent else {}, task.required_capabilities or {})]
        return [Candidate(server=s, project_server=None, layer="公司执行节点兜底", priority=10000, weight=10, max_concurrency=s.max_container_slots) for s in rows]

    def _score_candidates(self, candidates: list[Candidate]) -> list[tuple[int, Candidate]]:
        scored: list[tuple[int, Candidate]] = []
        for candidate in candidates:
            server = candidate.server
            running_total = self.db.scalar(select(func.count(CrawlerTaskRun.run_id)).where(CrawlerTaskRun.server_id == server.server_id, CrawlerTaskRun.run_status.in_(["ASSIGNED", "STARTING", "RUNNING", "CANCEL_REQUESTED"]))) or 0
            project_running = running_total
            if candidate.project_server:
                project_running = self.db.scalar(select(func.count(CrawlerTaskRun.run_id)).where(CrawlerTaskRun.server_id == server.server_id, CrawlerTaskRun.project_id == candidate.project_server.project_id, CrawlerTaskRun.run_status.in_(["ASSIGNED", "STARTING", "RUNNING", "CANCEL_REQUESTED"]))) or 0
            if running_total >= server.max_container_slots or project_running >= candidate.max_concurrency:
                continue
            score = candidate.priority * 100000 - candidate.weight * 100 + int(running_total) * 1000 + int(project_running) * 100
            if server.capacity_status == "PRESSURE":
                score += 10000
            scored.append((score, candidate))
        scored.sort(key=lambda item: item[0])
        return scored

    def _capabilities_match(self, actual: dict[str, Any], required: dict[str, Any]) -> bool:
        if not required:
            return True
        for key, expected in required.items():
            actual_value = actual.get(key)
            if isinstance(expected, list):
                if isinstance(actual_value, list):
                    if not all(item in actual_value for item in expected):
                        return False
                elif actual_value not in expected:
                    return False
            elif isinstance(expected, bool):
                if bool(actual_value) is not expected:
                    return False
            elif expected not in (None, "") and actual_value != expected:
                return False
        return True

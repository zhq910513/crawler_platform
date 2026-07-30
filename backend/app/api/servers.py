from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_admin
from app.models import CrawlerAgent, CrawlerServer, CrawlerServerMetric, SysUser
from app.services.audit import write_operation_log
from app.utils import utcnow

router = APIRouter(prefix="/servers", tags=["服务器"])


def server_dict(row: CrawlerServer, agent: CrawlerAgent | None, metric: CrawlerServerMetric | None) -> dict:
    online = bool(agent and agent.last_heartbeat_at and agent.last_heartbeat_at >= utcnow() - timedelta(seconds=90))
    return {
        "server_id": row.server_id,
        "server_code": row.server_code,
        "server_name": row.server_name,
        "server_ip": row.server_ip,
        "environment": row.environment,
        "max_container_slots": row.max_container_slots,
        "status": "ONLINE" if online else ("DISABLED" if row.status == "DISABLED" else "OFFLINE"),
        "description": row.description,
        "agent": {
            "agent_id": agent.agent_id,
            "agent_code": agent.agent_code,
            "agent_version": agent.agent_version,
            "protocol_version": agent.protocol_version,
            "instance_id": agent.instance_id,
            "capabilities": agent.capabilities_json,
            "labels": agent.labels_json,
            "hostname": agent.hostname,
            "os_name": agent.os_name,
            "python_version": agent.python_version,
            "docker_version": agent.docker_version,
            "status": agent.status,
            "last_heartbeat_at": agent.last_heartbeat_at,
            "last_error": agent.last_error,
        } if agent else None,
        "metric": {
            "cpu_percent": float(metric.cpu_percent),
            "memory_percent": float(metric.memory_percent),
            "disk_percent": float(metric.disk_percent),
            "load_1m": float(metric.load_1m),
            "load_5m": float(metric.load_5m),
            "running_task_count": metric.running_task_count,
            "process_count": metric.process_count,
            "docker_image_bytes": metric.docker_image_bytes,
            "recorded_at": metric.recorded_at,
        } if metric else None,
    }


@router.get("")
def list_servers(db: Session = Depends(get_db), _: SysUser = Depends(get_current_user)) -> list[dict]:
    rows = db.scalars(select(CrawlerServer).order_by(CrawlerServer.server_id.asc())).all()
    result = []
    for row in rows:
        agent = db.scalar(select(CrawlerAgent).where(CrawlerAgent.server_id == row.server_id))
        metric = db.scalar(
            select(CrawlerServerMetric).where(CrawlerServerMetric.server_id == row.server_id).order_by(CrawlerServerMetric.metric_id.desc()).limit(1)
        )
        result.append(server_dict(row, agent, metric))
    return result


@router.put("/{server_id}")
def update_server(
    server_id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(require_admin),
) -> dict:
    row = db.get(CrawlerServer, server_id)
    if not row:
        raise HTTPException(status_code=404, detail="服务器不存在")
    before = {"server_name": row.server_name, "max_container_slots": row.max_container_slots, "status": row.status}
    for field in ("server_name", "server_ip", "environment", "max_container_slots", "status", "description"):
        if field in payload:
            setattr(row, field, payload[field])
    after = {"server_name": row.server_name, "max_container_slots": row.max_container_slots, "status": row.status}
    write_operation_log(db, request, user, "UPDATE", "SERVER", row.server_id, before, after)
    db.commit()
    agent = db.scalar(select(CrawlerAgent).where(CrawlerAgent.server_id == row.server_id))
    metric = db.scalar(select(CrawlerServerMetric).where(CrawlerServerMetric.server_id == row.server_id).order_by(CrawlerServerMetric.metric_id.desc()).limit(1))
    return server_dict(row, agent, metric)


@router.get("/{server_id}/metrics")
def server_metrics(server_id: int, limit: int = 200, db: Session = Depends(get_db), _: SysUser = Depends(get_current_user)) -> list[dict]:
    rows = db.scalars(
        select(CrawlerServerMetric)
        .where(CrawlerServerMetric.server_id == server_id)
        .order_by(CrawlerServerMetric.metric_id.desc())
        .limit(min(max(limit, 1), 2000))
    ).all()
    return [
        {
            "cpu_percent": float(row.cpu_percent),
            "memory_percent": float(row.memory_percent),
            "disk_percent": float(row.disk_percent),
            "load_1m": float(row.load_1m),
            "load_5m": float(row.load_5m),
            "running_task_count": row.running_task_count,
            "recorded_at": row.recorded_at,
        }
        for row in reversed(rows)
    ]

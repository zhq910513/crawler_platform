from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CrawlerDeploymentLog,
    CrawlerProject,
    CrawlerProjectBootstrapToken,
    CrawlerSpiderEntry,
    CrawlerSpiderRelease,
    CrawlerTask,
    CrawlerTaskRuntime,
    CrawlerTaskSchedule,
)
from app.services.cron_service import next_run_utc, validate_cron
from app.services.project_manifest import normalize_project_manifest
from app.utils import sha256_text, utcnow


def create_project_bootstrap_token(
    db: Session,
    *,
    project: CrawlerProject,
    token_name: str,
    allowed_repo: str,
    expires_in_days: int | None,
    created_by: int | None,
) -> tuple[CrawlerProjectBootstrapToken, str]:
    raw = "cpbt_" + secrets.token_urlsafe(32)
    row = CrawlerProjectBootstrapToken(
        company_id=project.company_id,
        project_id=project.project_id,
        token_name=token_name,
        token_hash=sha256_text(raw),
        allowed_repo=allowed_repo or project.repository or "",
        permissions_json={
            "agent_register": True,
            "release_register": True,
            "entry_import": True,
            "deployment_report": True,
        },
        expires_at=utcnow() + timedelta(days=expires_in_days) if expires_in_days else None,
        status="ACTIVE",
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    return row, raw


def verify_project_bootstrap_token(db: Session, token: str) -> CrawlerProjectBootstrapToken | None:
    row = db.scalar(select(CrawlerProjectBootstrapToken).where(CrawlerProjectBootstrapToken.token_hash == sha256_text(token)))
    if not row or row.status != "ACTIVE":
        return None
    if row.expires_at and row.expires_at < utcnow():
        row.status = "EXPIRED"
        db.flush()
        return None
    row.last_used_at = utcnow()
    row.use_count += 1
    db.flush()
    return row


def write_deployment_log(
    db: Session,
    *,
    token_row: CrawlerProjectBootstrapToken,
    stage: str,
    status: str,
    message: str = "",
    server_code: str = "",
    agent_code: str = "",
    git_branch: str = "",
    git_commit: str = "",
    image_repository: str = "",
    image_digest: str = "",
    release_id: int | None = None,
    preflight: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
) -> CrawlerDeploymentLog:
    row = CrawlerDeploymentLog(
        company_id=token_row.company_id,
        project_id=token_row.project_id,
        token_id=token_row.token_id,
        server_code=server_code,
        agent_code=agent_code,
        stage=stage,
        status=status,
        message=message[:4000],
        git_branch=git_branch,
        git_commit=git_commit,
        image_repository=image_repository,
        image_digest=image_digest,
        release_id=release_id,
        preflight_json=preflight,
        result_json=result,
    )
    db.add(row)
    db.flush()
    return row


def _schedule_from_suggested(suggested: dict[str, Any]) -> tuple[str, str, str, bool]:
    # Only a hint for first import. Production schedule remains disabled until
    # an operator configures it in the platform.
    if suggested.get("type") == "cron" and suggested.get("cron"):
        return "CRON", str(suggested.get("cron", "")), str(suggested.get("timezone") or "Asia/Shanghai"), False
    if suggested.get("type") == "cron":
        minute = str(suggested.get("minute", "0"))
        hour = str(suggested.get("hour", "0"))
        day = str(suggested.get("day", "*"))
        month = str(suggested.get("month", "*"))
        dow = str(suggested.get("day_of_week", "*"))
        return "CRON", f"{minute} {hour} {day} {month} {dow}", str(suggested.get("timezone") or "Asia/Shanghai"), False
    return "MANUAL", "", "Asia/Shanghai", False


def import_project_entries(
    db: Session,
    *,
    project: CrawlerProject,
    release: CrawlerSpiderRelease,
    project_manifest: dict[str, Any],
) -> dict[str, Any]:
    descriptors = normalize_project_manifest(project_manifest)
    imported: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    release_entries = {row.task_name for row in db.scalars(select(CrawlerSpiderEntry).where(CrawlerSpiderEntry.release_id == release.release_id)).all()}
    for item in descriptors:
        existing = db.scalar(
            select(CrawlerTask).where(
                CrawlerTask.project_id == project.project_id,
                CrawlerTask.entry_module == item["entry_module"],
                CrawlerTask.entry_function == item["entry_function"],
            )
        )
        if existing:
            skipped.append({"reason": "DUPLICATE_ENTRY", "task_id": existing.task_id, "entry": f"{item['entry_module']}:{item['entry_function']}"})
            continue
        if item["spider_task_name"] not in release_entries:
            failed.append({"reason": "MISSING_RELEASE_ENTRY", "spider_task_name": item["spider_task_name"]})
            continue
        base_code = f"{project.project_code}.{item['task_code']}"[:120]
        task_code = base_code
        index = 2
        while db.scalar(select(CrawlerTask).where(CrawlerTask.task_code == task_code)):
            suffix = f".{index}"
            task_code = (base_code[: 120 - len(suffix)] + suffix)
            index += 1
        task = CrawlerTask(
            company_id=project.company_id,
            project_id=project.project_id,
            task_code=task_code,
            task_name=item["task_name"],
            spider_task_name=item["spider_task_name"],
            platform=item["platform"],
            task_group=item["platform"] or "default",
            developer="",
            entry_module=item["entry_module"],
            entry_function=item["entry_function"],
            source_type="PROJECT_MANIFEST",
            source_file=item["source_file"],
            source_fingerprint=item["source_fingerprint"],
            resource_requirements=item["resources"],
            parameters=item["default_parameters"],
            status="DISABLED",
            description=item["description"],
        )
        db.add(task)
        db.flush()
        db.add(CrawlerTaskRuntime(
            task_id=task.task_id,
            image_policy="RELEASE_CHANNEL",
            release_channel="stable",
            fixed_spider_release_id=None,
            pull_policy="IF_NOT_PRESENT",
            cpu_limit=2,
            memory_limit_mb=4096,
            shm_size_mb=256,
            pids_limit=512,
            stop_grace_seconds=30,
            auto_remove=True,
            keep_failed_container=False,
        ))
        schedule_type, cron, timezone, enabled = _schedule_from_suggested(item["suggested_trigger"])
        if schedule_type == "CRON" and cron:
            validate_cron(cron, timezone)
        db.add(CrawlerTaskSchedule(
            task_id=task.task_id,
            schedule_type=schedule_type,
            cron_expression=cron,
            timezone=timezone,
            enabled=enabled,
            next_run_at=next_run_utc(cron, timezone) if schedule_type == "CRON" and enabled else None,
        ))
        imported.append({"task_id": task.task_id, "task_code": task.task_code, "entry": f"{item['entry_module']}:{item['entry_function']}"})
    db.flush()
    return {"imported": imported, "skipped": skipped, "failed": failed}

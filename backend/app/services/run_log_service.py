from __future__ import annotations

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import CrawlerAgent, CrawlerRunEvent, CrawlerRunLogChunk, CrawlerTaskRun, SysUser
from app.schemas import AgentRunEventCreate, AgentRunLogChunkCreate, AgentRunLogFinalizeCreate, RunLogTailQuery
from app.services.permissions import require_project_role
from app.utils import utcnow

MAX_CHUNK_BYTES = 256 * 1024
DEFAULT_LOG_LIMIT_MB = 20


class RunLogService:
    def __init__(self, db: Session):
        self.db = db

    def append_event(self, agent: CrawlerAgent, payload: AgentRunEventCreate) -> dict:
        run = self._agent_run(agent, payload.run_id, payload.lease_token, payload.agent_instance_id)
        event = CrawlerRunEvent(
            company_id=run.company_id,
            run_id=run.run_id,
            event_type=payload.event_type,
            event_level=payload.event_level,
            stage=payload.stage,
            message=payload.message,
            payload_json=payload.payload,
        )
        self.db.add(event)
        self._apply_event_diagnosis(run, payload)
        self.db.commit()
        return {"eventId": event.event_id}

    def append_chunk(self, agent: CrawlerAgent, payload: AgentRunLogChunkCreate) -> dict:
        run = self._agent_run(agent, payload.run_id, payload.lease_token, payload.agent_instance_id)
        content = payload.content or ""
        size = len(content.encode("utf-8", errors="replace"))
        log_limit = max(1, int(run.log_limit_mb or DEFAULT_LOG_LIMIT_MB)) * 1024 * 1024
        if run.log_bytes >= log_limit:
            run.log_truncated = True
            run.log_status = "TRUNCATED"
            self.db.commit()
            return {"accepted": False, "logTruncated": True, "lastLogSeq": run.last_log_seq}
        if size > MAX_CHUNK_BYTES:
            raise AppError("日志分片过大", code=40091, http_status=status.HTTP_400_BAD_REQUEST)
        chunk = CrawlerRunLogChunk(
            company_id=run.company_id,
            run_id=run.run_id,
            stream=payload.stream,
            seq=payload.seq,
            offset_start=payload.offset_start,
            offset_end=payload.offset_end,
            content=content,
            content_size=size,
        )
        self.db.add(chunk)
        run.log_status = "UPLOADING"
        run.last_log_seq = max(int(run.last_log_seq or 0), payload.seq)
        run.last_log_at = utcnow()
        run.log_bytes = int(run.log_bytes or 0) + size
        run.log_lines = int(run.log_lines or 0) + content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        if run.log_bytes >= log_limit:
            run.log_truncated = True
            run.log_status = "TRUNCATED"
        self.db.commit()
        return {"accepted": True, "lastLogSeq": run.last_log_seq, "logTruncated": run.log_truncated}

    def finalize(self, agent: CrawlerAgent, payload: AgentRunLogFinalizeCreate) -> dict:
        run = self._agent_run(agent, payload.run_id, payload.lease_token, payload.agent_instance_id)
        run.log_status = payload.log_status
        run.log_path = payload.log_path
        run.log_truncated = payload.log_truncated or bool(run.log_truncated)
        run.failed_stage = payload.failed_stage
        run.error_type = payload.error_type
        run.error_summary = payload.error_summary
        run.retryable = payload.retryable
        run.diagnosis_json = payload.diagnosis or {}
        if payload.error_summary and not run.error_message:
            run.error_message = payload.error_summary
        self.db.commit()
        return {"runId": run.run_id, "logStatus": run.log_status, "logTruncated": run.log_truncated}

    def list_events(self, current_user: SysUser, run_id: int) -> list[CrawlerRunEvent]:
        run = self._user_run(current_user, run_id)
        return list(self.db.scalars(select(CrawlerRunEvent).where(CrawlerRunEvent.run_id == run.run_id).order_by(CrawlerRunEvent.created_at.asc(), CrawlerRunEvent.event_id.asc())).all())

    def tail_logs(self, current_user: SysUser, run_id: int, query: RunLogTailQuery) -> dict:
        run = self._user_run(current_user, run_id)
        stmt = select(CrawlerRunLogChunk).where(CrawlerRunLogChunk.run_id == run.run_id, CrawlerRunLogChunk.seq > query.after_seq)
        if query.stream:
            stmt = stmt.where(CrawlerRunLogChunk.stream == query.stream)
        stmt = stmt.order_by(CrawlerRunLogChunk.seq.asc()).limit(query.limit)
        chunks = list(self.db.scalars(stmt).all())
        if query.keyword:
            chunks = [chunk for chunk in chunks if query.keyword in chunk.content]
        return {"runId": run.run_id, "lastLogSeq": run.last_log_seq, "logTruncated": run.log_truncated, "chunks": chunks}

    def download_logs(self, current_user: SysUser, run_id: int) -> dict:
        run = self._user_run(current_user, run_id)
        chunks = list(self.db.scalars(select(CrawlerRunLogChunk).where(CrawlerRunLogChunk.run_id == run.run_id).order_by(CrawlerRunLogChunk.seq.asc())).all())
        content = "".join(chunk.content for chunk in chunks)
        return {"filename": f"run-{run.run_id}.log", "content": content, "logTruncated": run.log_truncated, "logBytes": run.log_bytes}

    def diagnosis(self, current_user: SysUser, run_id: int) -> dict:
        run = self._user_run(current_user, run_id)
        return {
            "runId": run.run_id,
            "failedStage": run.failed_stage,
            "errorType": run.error_type,
            "errorSummary": run.error_summary or run.error_message,
            "retryable": run.retryable,
            "diagnosis": run.diagnosis_json or {},
            "logStatus": run.log_status,
            "logTruncated": run.log_truncated,
            "lastLogSeq": run.last_log_seq,
            "lastLogAt": run.last_log_at,
        }

    def _agent_run(self, agent: CrawlerAgent, run_id: int, lease_token: str, agent_instance_id: str | None) -> CrawlerTaskRun:
        if agent_instance_id and agent_instance_id != agent.agent_instance_id:
            raise AppError("Agent 实例已被替代", code=40373, http_status=status.HTTP_403_FORBIDDEN)
        run = self.db.get(CrawlerTaskRun, run_id)
        if not run or run.agent_id != agent.agent_id or run.lease_token != lease_token:
            raise AppError("运行租约无效", code=40370, http_status=status.HTTP_403_FORBIDDEN)
        return run

    def _user_run(self, current_user: SysUser, run_id: int) -> CrawlerTaskRun:
        run = self.db.get(CrawlerTaskRun, run_id)
        if not run:
            raise AppError("运行实例不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        require_project_role(self.db, current_user, run.project_id, "VIEWER")
        return run

    @staticmethod
    def _apply_event_diagnosis(run: CrawlerTaskRun, payload: AgentRunEventCreate) -> None:
        extra = payload.payload or {}
        if payload.event_level in {"ERROR", "CRITICAL"}:
            run.failed_stage = payload.stage or run.failed_stage
            run.error_type = str(extra.get("errorType") or run.error_type or "UNKNOWN_ERROR")[:100]
            run.error_summary = (payload.message or run.error_summary or run.error_message)[:1000]
            retryable = extra.get("retryable")
            if isinstance(retryable, bool):
                run.retryable = retryable

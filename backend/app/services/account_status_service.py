from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import timedelta
from typing import Any

from fastapi import status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import CrawlerAccountCredential, CrawlerAccountStatusEvent, CrawlerAgent, CrawlerCompany, CrawlerCredentialLease, CrawlerCredentialSubjectBinding, SysUser
from app.schemas import AccountStatusEventCreate, CredentialLeaseAcquire, CredentialLeaseRelease, CredentialSubjectBindingCreate, CredentialSubjectBindingUpdate
from app.services.permissions import is_super_admin, require_company_scope, scoped_company_id
from app.utils import utcnow

_SUCCESS_CODES = {"LOGIN_OK", "COOKIE_OK", "TOKEN_OK", "ACCOUNT_OK", "AUTH_OK", "SUBJECT_QUERY_OK", "SUBJECT_BINDING_CREATED", "TOKEN_REFRESH_OK"}
_EXPIRED_CODES = {"COOKIE_EXPIRED", "TOKEN_EXPIRED", "AUTH_EXPIRED", "REFRESH_TOKEN_EXPIRED"}
_INVALID_CODES = {"COOKIE_INVALID", "TOKEN_INVALID", "PASSWORD_INVALID", "ACCOUNT_DISABLED_BY_PLATFORM", "ACCOUNT_LOCKED_BY_PLATFORM", "APP_KEY_INVALID", "APP_SECRET_INVALID", "SIGNATURE_INVALID"}
_MANUAL_CODES = {"CAPTCHA_REQUIRED", "EMAIL_VERIFY_REQUIRED", "PHONE_VERIFY_REQUIRED", "TWO_FACTOR_REQUIRED", "LOGIN_FAILED"}
_RATE_CODES = {"RATE_LIMITED", "QUOTA_LIMITED", "API_QUOTA_LIMITED"}
_NEUTRAL_CODES = {"NETWORK_ERROR", "PLATFORM_5XX", "PLATFORM_MAINTENANCE", "GATEWAY_5XX", "SUBJECT_NOT_FOUND", "SUBJECT_NO_PERMISSION", "SUBJECT_QUERY_FAILED"}

_SENSITIVE_KEY = re.compile(r"(?:password|passwd|pwd|secret|token|cookie|authorization|access[_-]?key|private[_-]?key|email[_-]?token|phone|mobile)", re.I)
_SENSITIVE_TEXT = re.compile(r"(?i)(cookie|token|password|passwd|pwd|secret|authorization|email_token|phone_number|access_key)\s*[:=]\s*([^\s,;]+)")


def _sanitize_text(value: str, limit: int = 1000) -> str:
    text = (value or "").strip()
    text = _SENSITIVE_TEXT.sub(lambda m: f"{m.group(1)}=***REDACTED***", text)
    return text[:limit]


def _sanitize_payload(value: Any, *, key: str | None = None, depth: int = 0) -> Any:
    if key and _SENSITIVE_KEY.search(key):
        return "***REDACTED***"
    if depth > 8:
        return "<max-depth>"
    if isinstance(value, dict):
        return {str(k): _sanitize_payload(v, key=str(k), depth=depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_payload(v, depth=depth + 1) for v in value]
    if isinstance(value, str):
        return _sanitize_text(value, 500)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:500]


def _lease_token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _status_mapping(status_code: str) -> tuple[str, str, str, bool, int]:
    code = (status_code or "").upper()
    if code in _SUCCESS_CODES:
        return "HEALTHY", "AUTH_ACTIVE", "AVAILABLE", True, 4
    if code in _EXPIRED_CODES:
        return "EXPIRED", "AUTH_EXPIRED", "AVAILABLE", False, 1
    if code in _INVALID_CODES:
        return "INVALID", "AUTH_INVALID", "LOCKED", False, 1
    if code in _MANUAL_CODES:
        return "NEED_VERIFY", "MANUAL_REQUIRED", "COOLDOWN", False, 1
    if code in _RATE_CODES:
        return "WARNING", "AUTH_ACTIVE", "COOLDOWN", False, 1
    if code in _NEUTRAL_CODES:
        return "WARNING", "AUTH_ACTIVE", "AVAILABLE", False, 1
    if code.endswith("_OK"):
        return "HEALTHY", "AUTH_ACTIVE", "AVAILABLE", True, 4
    return "WARNING", "AUTH_ACTIVE", "AVAILABLE", False, 1


class AccountStatusService:
    def __init__(self, db: Session):
        self.db = db

    def list_credentials(self, user: SysUser, company_id: int | None = None, platform_code: str = "", credential_key: str = "") -> list[CrawlerAccountCredential]:
        scoped = scoped_company_id(user, company_id)
        stmt = select(CrawlerAccountCredential).order_by(CrawlerAccountCredential.updated_at.desc())
        if scoped is not None:
            stmt = stmt.where(CrawlerAccountCredential.company_id == scoped)
        if platform_code:
            stmt = stmt.where(CrawlerAccountCredential.platform_code == platform_code)
        if credential_key:
            stmt = stmt.where(CrawlerAccountCredential.credential_key == credential_key)
        return list(self.db.scalars(stmt.limit(500)).all())

    def list_events(self, user: SysUser, credential_id: int, limit: int = 100) -> list[CrawlerAccountStatusEvent]:
        credential = self.db.get(CrawlerAccountCredential, credential_id)
        if not credential:
            raise AppError("资源不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        require_company_scope(user, credential.company_id)
        return list(self.db.scalars(select(CrawlerAccountStatusEvent).where(CrawlerAccountStatusEvent.credential_id == credential_id).order_by(CrawlerAccountStatusEvent.created_at.desc()).limit(limit)).all())


    def list_subject_bindings(self, user: SysUser, company_id: int | None = None, platform_code: str = "", subject_type: str = "", credential_key: str = "") -> list[CrawlerCredentialSubjectBinding]:
        scoped = scoped_company_id(user, company_id)
        stmt = select(CrawlerCredentialSubjectBinding).order_by(CrawlerCredentialSubjectBinding.updated_at.desc())
        if scoped is not None:
            stmt = stmt.where(CrawlerCredentialSubjectBinding.company_id == scoped)
        if platform_code:
            stmt = stmt.where(CrawlerCredentialSubjectBinding.platform_code == platform_code.strip().lower())
        if subject_type:
            stmt = stmt.where(CrawlerCredentialSubjectBinding.subject_type == subject_type)
        if credential_key:
            stmt = stmt.where(CrawlerCredentialSubjectBinding.credential_key == credential_key)
        return list(self.db.scalars(stmt.limit(500)).all())

    def create_subject_binding(self, user: SysUser, payload: CredentialSubjectBindingCreate) -> CrawlerCredentialSubjectBinding:
        company = self._resolve_company(payload.company_id, payload.company_code)
        require_company_scope(user, company.company_id)
        credential = self._ensure_credential(company, payload.platform_code.strip().lower(), payload.credential_key, payload.credential_key)
        now = utcnow()
        binding = self.db.scalar(select(CrawlerCredentialSubjectBinding).where(
            CrawlerCredentialSubjectBinding.company_id == company.company_id,
            CrawlerCredentialSubjectBinding.platform_code == payload.platform_code.strip().lower(),
            CrawlerCredentialSubjectBinding.subject_type == payload.subject_type,
            CrawlerCredentialSubjectBinding.subject_key == payload.subject_key,
        ))
        if binding and binding.credential_key != payload.credential_key and binding.rebinding_policy == "STRICT":
            raise AppError("对象账号绑定处于严格模式，不能自动换绑", code=40080, http_status=status.HTTP_400_BAD_REQUEST)
        if not binding:
            binding = CrawlerCredentialSubjectBinding(
                company_id=company.company_id, company_code=company.company_code, platform_code=payload.platform_code.strip().lower(),
                subject_type=payload.subject_type, subject_key=payload.subject_key, subject_name=payload.subject_name,
                credential_id=credential.credential_id, credential_key=payload.credential_key, binding_policy=payload.binding_policy,
                rebinding_policy=payload.rebinding_policy, source="ADMIN", first_success_at=now, last_success_at=now, metadata_json=payload.metadata,
            )
            self.db.add(binding)
        else:
            binding.subject_name = payload.subject_name or binding.subject_name
            binding.credential_id = credential.credential_id
            binding.credential_key = payload.credential_key
            binding.binding_status = "ACTIVE"
            binding.rebinding_policy = payload.rebinding_policy
            binding.metadata_json = {**(binding.metadata_json or {}), **(payload.metadata or {})}
            binding.updated_at = now
        self.db.commit()
        return binding

    def update_subject_binding(self, user: SysUser, binding_id: int, payload: CredentialSubjectBindingUpdate) -> CrawlerCredentialSubjectBinding:
        binding = self.db.get(CrawlerCredentialSubjectBinding, binding_id)
        if not binding:
            raise AppError("资源不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        require_company_scope(user, binding.company_id)
        if payload.credential_key and payload.credential_key != binding.credential_key:
            credential = self._ensure_credential(self._resolve_company(binding.company_id, None), binding.platform_code, payload.credential_key, payload.credential_key)
            binding.credential_id = credential.credential_id
            binding.credential_key = payload.credential_key
            binding.binding_status = "REBOUND"
            binding.metadata_json = {**(binding.metadata_json or {}), "lastRebindReason": payload.reason}
        if payload.binding_status:
            binding.binding_status = payload.binding_status
        if payload.rebinding_policy:
            binding.rebinding_policy = payload.rebinding_policy
        if payload.metadata is not None:
            binding.metadata_json = {**(binding.metadata_json or {}), **payload.metadata}
        self.db.commit()
        return binding

    def list_leases(self, user: SysUser, company_id: int | None = None, platform_code: str = "", credential_key: str = "") -> list[CrawlerCredentialLease]:
        scoped = scoped_company_id(user, company_id)
        stmt = select(CrawlerCredentialLease).order_by(CrawlerCredentialLease.updated_at.desc())
        if scoped is not None:
            stmt = stmt.where(CrawlerCredentialLease.company_id == scoped)
        if platform_code:
            stmt = stmt.where(CrawlerCredentialLease.platform_code == platform_code.strip().lower())
        if credential_key:
            stmt = stmt.where(CrawlerCredentialLease.credential_key == credential_key.strip())
        return list(self.db.scalars(stmt.limit(500)).all())

    def acquire_lease(self, user: SysUser | None, payload: CredentialLeaseAcquire, *, agent: CrawlerAgent | None = None) -> dict[str, Any]:
        company = self._resolve_company(agent.company_id if agent else payload.company_id, payload.company_code)
        if agent:
            if payload.company_id and payload.company_id != agent.company_id:
                raise AppError("Agent 不允许租用其他公司的账号", code=40376, http_status=status.HTTP_403_FORBIDDEN)
        elif user:
            require_company_scope(user, company.company_id)
        else:
            raise AppError("缺少调用身份", code=40101, http_status=status.HTTP_401_UNAUTHORIZED)
        platform_code = payload.platform_code.strip().lower()
        credential_key = payload.credential_key.strip()
        credential = self._ensure_credential(company, platform_code, credential_key, credential_key)
        # MySQL/InnoDB 上锁住账号行，序列化同一账号的租约申请，避免账号池并发双占。
        locked_credential = self.db.scalar(select(CrawlerAccountCredential).where(
            CrawlerAccountCredential.credential_id == credential.credential_id,
        ).with_for_update())
        if locked_credential:
            credential = locked_credential
        now = utcnow()
        # 主动清理过期 ACTIVE 租约，避免异常退出永久占用账号。
        expired = list(self.db.scalars(select(CrawlerCredentialLease).where(
            CrawlerCredentialLease.company_id == company.company_id,
            CrawlerCredentialLease.platform_code == platform_code,
            CrawlerCredentialLease.credential_key == credential_key,
            CrawlerCredentialLease.lease_status == "ACTIVE",
            CrawlerCredentialLease.lease_until < now,
        )).all())
        for row in expired:
            row.lease_status = "EXPIRED"
            row.release_reason = "lease expired"
            row.released_at = now
        active = self.db.scalar(select(CrawlerCredentialLease).where(
            CrawlerCredentialLease.company_id == company.company_id,
            CrawlerCredentialLease.platform_code == platform_code,
            CrawlerCredentialLease.credential_key == credential_key,
            CrawlerCredentialLease.lease_status == "ACTIVE",
        ).with_for_update())
        if active:
            raise AppError("账号当前存在有效租约，不能重复占用", code=40980, http_status=status.HTTP_409_CONFLICT, data={"leaseId": active.lease_id, "leaseUntil": active.lease_until.isoformat() if active.lease_until else None})
        if not credential.enabled or credential.usage_status in {"LOCKED", "COOLDOWN", "QUOTA_LIMITED"}:
            raise AppError("账号当前状态不可租用", code=40981, http_status=status.HTTP_409_CONFLICT, data={"credentialKey": credential_key, "healthStatus": credential.health_status, "usageStatus": credential.usage_status})
        token = "lease_" + secrets.token_urlsafe(24)
        lease = CrawlerCredentialLease(
            company_id=company.company_id,
            company_code=company.company_code,
            platform_code=platform_code,
            credential_id=credential.credential_id,
            credential_key=credential_key,
            slot=payload.slot or "",
            run_id=payload.run_id,
            task_id=payload.task_id,
            agent_id=agent.agent_id if agent else None,
            agent_code=(agent.agent_code if agent else payload.agent_code) or "",
            lease_status="ACTIVE",
            lease_token_hash=_lease_token_hash(token),
            lease_until=now + timedelta(seconds=payload.lease_seconds),
            heartbeat_at=now,
            metadata_json=_sanitize_payload(payload.metadata),
        )
        credential.usage_status = "IN_USE"
        self.db.add(lease)
        self.db.commit()
        return {"lease": lease, "leaseToken": token}

    def release_lease(self, user: SysUser | None, payload: CredentialLeaseRelease, *, agent: CrawlerAgent | None = None) -> CrawlerCredentialLease:
        stmt = select(CrawlerCredentialLease)
        if payload.lease_id:
            stmt = stmt.where(CrawlerCredentialLease.lease_id == payload.lease_id)
        else:
            stmt = stmt.where(CrawlerCredentialLease.lease_token_hash == _lease_token_hash(payload.lease_token or ""))
        lease = self.db.scalar(stmt.with_for_update())
        if not lease:
            raise AppError("账号租约不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        if agent and lease.agent_id not in {None, agent.agent_id}:
            raise AppError("Agent 不允许释放其他 Agent 的账号租约", code=40377, http_status=status.HTTP_403_FORBIDDEN)
        if user:
            require_company_scope(user, lease.company_id)
        now = utcnow()
        lease.lease_status = "RELEASED" if lease.lease_status == "ACTIVE" else lease.lease_status
        lease.released_at = now
        lease.release_reason = payload.reason or "completed"
        credential = self.db.get(CrawlerAccountCredential, lease.credential_id) if lease.credential_id else None
        if credential:
            other_active = self.db.scalar(select(CrawlerCredentialLease).where(
                CrawlerCredentialLease.credential_id == credential.credential_id,
                CrawlerCredentialLease.lease_status == "ACTIVE",
                CrawlerCredentialLease.lease_id != lease.lease_id,
                CrawlerCredentialLease.lease_until >= now,
            ))
            if not other_active and credential.usage_status == "IN_USE":
                credential.usage_status = "AVAILABLE"
        self.db.commit()
        return lease

    def set_enabled(self, user: SysUser, credential_id: int, enabled: bool) -> CrawlerAccountCredential:
        credential = self.db.get(CrawlerAccountCredential, credential_id)
        if not credential:
            raise AppError("资源不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        require_company_scope(user, credential.company_id)
        credential.enabled = enabled
        if not enabled:
            credential.usage_status = "LOCKED"
            credential.health_status = "DISABLED"
        elif credential.health_status == "DISABLED":
            credential.health_status = "UNKNOWN"
            credential.usage_status = "AVAILABLE"
        self.db.commit()
        return credential

    def ingest_user_event(self, user: SysUser, payload: AccountStatusEventCreate) -> CrawlerAccountStatusEvent:
        company = self._resolve_company(payload.company_id, payload.company_code)
        require_company_scope(user, company.company_id)
        return self._ingest(payload, company=company, agent=None)

    def ingest_agent_event(self, agent: CrawlerAgent, payload: AccountStatusEventCreate) -> CrawlerAccountStatusEvent:
        company = self._resolve_company(agent.company_id, payload.company_code)
        if payload.company_id and payload.company_id != agent.company_id:
            raise AppError("Agent 不允许上报其他公司的账号状态", code=40375, http_status=status.HTTP_403_FORBIDDEN)
        return self._ingest(payload, company=company, agent=agent)

    def _resolve_company(self, company_id: int | None, company_code: str | None) -> CrawlerCompany:
        stmt = select(CrawlerCompany)
        if company_id:
            stmt = stmt.where(CrawlerCompany.company_id == company_id)
        elif company_code:
            stmt = stmt.where(CrawlerCompany.company_code == company_code)
        company = self.db.scalar(stmt)
        if not company:
            raise AppError("公司不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        return company


    def _ensure_credential(self, company: CrawlerCompany, platform_code: str, credential_key: str, credential_name: str = "") -> CrawlerAccountCredential:
        credential = self.db.scalar(select(CrawlerAccountCredential).where(
            CrawlerAccountCredential.company_id == company.company_id,
            CrawlerAccountCredential.platform_code == platform_code,
            CrawlerAccountCredential.credential_key == credential_key,
        ))
        if not credential:
            credential = CrawlerAccountCredential(
                company_id=company.company_id,
                company_code=company.company_code,
                platform_code=platform_code,
                credential_key=credential_key,
                credential_name=credential_name or credential_key,
            )
            self.db.add(credential)
            self.db.flush()
        return credential

    def _apply_subject_event(self, payload: AccountStatusEventCreate, company: CrawlerCompany, credential: CrawlerAccountCredential, event: CrawlerAccountStatusEvent, success: bool, observed_at) -> None:
        subject_type = (payload.subject_type or "").strip()
        subject_key = (payload.subject_key or "").strip()
        if not subject_type or not subject_key:
            return
        binding = self.db.scalar(select(CrawlerCredentialSubjectBinding).where(
            CrawlerCredentialSubjectBinding.company_id == company.company_id,
            CrawlerCredentialSubjectBinding.platform_code == credential.platform_code,
            CrawlerCredentialSubjectBinding.subject_type == subject_type,
            CrawlerCredentialSubjectBinding.subject_key == subject_key,
        ).with_for_update())
        if success:
            if not binding:
                # 首次成功绑定是唯一关键区。先写 PENDING/ACTIVE 并 flush，依赖唯一约束防止并发双绑。
                binding = CrawlerCredentialSubjectBinding(
                    company_id=company.company_id, company_code=company.company_code, platform_code=credential.platform_code,
                    subject_type=subject_type, subject_key=subject_key, subject_name=payload.subject_name or "",
                    credential_id=credential.credential_id, credential_key=credential.credential_key, binding_status="ACTIVE",
                    binding_policy="BIND_ON_SUCCESS", rebinding_policy="MANUAL_ONLY", source=payload.source,
                    first_success_run_id=payload.run_id, first_success_task_id=payload.task_id, first_success_agent_code=event.agent_code,
                    first_success_at=observed_at, last_success_run_id=payload.run_id, last_success_at=observed_at,
                    metadata_json={"createdByEventUid": event.event_uid, **(_sanitize_payload(payload.payload or {}) if isinstance(payload.payload, dict) else {})},
                )
                try:
                    with self.db.begin_nested():
                        self.db.add(binding)
                        self.db.flush()
                except IntegrityError:
                    # 并发场景下另一个 run 先成功绑定。重新查询并记录冲突，不覆盖既有绑定。
                    existing = self.db.scalar(select(CrawlerCredentialSubjectBinding).where(
                        CrawlerCredentialSubjectBinding.company_id == company.company_id,
                        CrawlerCredentialSubjectBinding.platform_code == credential.platform_code,
                        CrawlerCredentialSubjectBinding.subject_type == subject_type,
                        CrawlerCredentialSubjectBinding.subject_key == subject_key,
                    ))
                    if existing:
                        event.payload_sanitized = {**(event.payload_sanitized or {}), "subjectBindingConflict": {"existingCredentialKey": existing.credential_key, "reportedCredentialKey": credential.credential_key}}
                    return
            elif binding.credential_key == credential.credential_key:
                binding.binding_status = "ACTIVE" if binding.binding_status in {"PENDING", "FAILED"} else binding.binding_status
                binding.subject_name = payload.subject_name or binding.subject_name
                binding.last_success_run_id = payload.run_id
                binding.last_success_at = observed_at
                binding.failure_count = 0
                binding.last_error_code = ""
                binding.last_error_summary = ""
            else:
                event.payload_sanitized = {**(event.payload_sanitized or {}), "subjectBindingConflict": {"existingCredentialKey": binding.credential_key, "reportedCredentialKey": credential.credential_key}}
        else:
            if binding:
                binding.last_failure_at = observed_at
                binding.failure_count = int(binding.failure_count or 0) + 1
                binding.last_error_code = payload.status_code.upper()
                binding.last_error_summary = event.message_sanitized

    def _ingest(self, payload: AccountStatusEventCreate, *, company: CrawlerCompany, agent: CrawlerAgent | None) -> CrawlerAccountStatusEvent:
        platform_code = payload.platform_code.strip().lower()
        credential_key = payload.credential_key.strip()
        now = utcnow()
        event_uid = payload.event_uid or f"acctevt_{uuid.uuid4().hex}"
        existing = self.db.scalar(select(CrawlerAccountStatusEvent).where(CrawlerAccountStatusEvent.event_uid == event_uid))
        if existing:
            return existing
        credential = self._ensure_credential(company, platform_code, credential_key, payload.credential_name or credential_key)
        health, login, usage, success, fresh_hours = _status_mapping(payload.status_code)
        observed_at = payload.observed_at or now
        event = CrawlerAccountStatusEvent(
            event_uid=event_uid,
            company_id=company.company_id,
            company_code=company.company_code,
            platform_code=platform_code,
            credential_key=credential_key,
            credential_id=credential.credential_id,
            run_id=payload.run_id,
            task_id=payload.task_id,
            agent_id=agent.agent_id if agent else None,
            agent_code=(agent.agent_code if agent else payload.agent_code) or "",
            slot=payload.slot or "",
            subject_type=payload.subject_type or "",
            subject_key=payload.subject_key or "",
            subject_name=payload.subject_name or "",
            affects_credential=payload.affects_credential,
            event_type=payload.event_type,
            status_code=payload.status_code.upper(),
            severity=payload.severity,
            source=payload.source,
            message_sanitized=_sanitize_text(payload.message),
            observed_at=observed_at,
            payload_sanitized=_sanitize_payload(payload.payload),
        )
        self.db.add(event)
        if payload.affects_credential:
            if credential.enabled:
                credential.health_status = health
                credential.login_status = login
                credential.usage_status = usage
            credential.last_status_code = payload.status_code.upper()
            credential.last_status_source = payload.source
            credential.last_verified_at = observed_at
            credential.last_verified_agent_code = event.agent_code
            credential.last_run_id = payload.run_id
            credential.last_task_id = payload.task_id
            credential.status_fresh_until = observed_at + timedelta(hours=fresh_hours)
            credential.status_metadata = {
                **(credential.status_metadata or {}),
                "lastEventUid": event_uid,
                "lastSeverity": payload.severity,
                "lastSlot": payload.slot or "",
                "statusFreshHours": fresh_hours,
            }
            if success:
                credential.last_success_at = observed_at
                credential.failure_count = 0
                credential.last_error_summary = ""
            elif payload.status_code.upper() not in _NEUTRAL_CODES:
                credential.last_failure_at = observed_at
                credential.failure_count = int(credential.failure_count or 0) + 1
                credential.last_error_summary = event.message_sanitized
        else:
            credential.status_metadata = {
                **(credential.status_metadata or {}),
                "lastNonCredentialIssue": payload.status_code.upper(),
                "lastNonCredentialEventUid": event_uid,
                "lastNonCredentialObservedAt": observed_at.isoformat() if observed_at else "",
            }
        self._apply_subject_event(payload, company, credential, event, success, observed_at)
        self.db.commit()
        return event

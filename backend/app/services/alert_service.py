from __future__ import annotations

import json
import smtplib
from datetime import timedelta
from email.message import EmailMessage
from typing import Any

import requests
from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import SysAlertDelivery, SysAlertEvent, SysNotificationChannel, SysUser
from app.repositories.platform import NotificationRepository
from app.schemas import NotificationChannelCreate, NotificationChannelTest, NotificationChannelUpdate
from app.security import decrypt_secret, encrypt_secret
from app.services.permissions import require_super_admin
from app.services.audit import write_operation_log
from app.utils import utcnow


class AlertService:
    def __init__(self, db: Session):
        self.db = db
        self.channels = NotificationRepository(db)

    @staticmethod
    def public_channel(channel: SysNotificationChannel) -> dict:
        return {"channelId": channel.channel_id, "scopeType": channel.scope_type, "companyId": channel.company_id, "projectId": channel.project_id, "channelName": channel.channel_name, "channelType": channel.channel_type, "channelStatus": channel.channel_status, "p0Only": channel.p0_only, "lastTestAt": channel.last_test_at, "lastTestResult": channel.last_test_result, "cooldownSeconds": channel.cooldown_seconds, "createdAt": channel.created_at}

    def list_channels(self, user: SysUser) -> list[dict]:
        require_super_admin(user)
        return [self.public_channel(item) for item in self.channels.list_channels()]

    def create_channel(self, user: SysUser, payload: NotificationChannelCreate) -> dict:
        require_super_admin(user)
        channel = SysNotificationChannel(scope_type=payload.scope_type, company_id=payload.company_id, project_id=payload.project_id, channel_name=payload.channel_name, channel_type=payload.channel_type, channel_status=payload.channel_status, config_encrypted=encrypt_secret(json.dumps(payload.config, ensure_ascii=False)), p0_only=True, cooldown_seconds=payload.cooldown_seconds)
        self.channels.add(channel)
        self.db.flush()
        write_operation_log(self.db, user, None, operation_type="CREATE_NOTIFICATION_CHANNEL", resource_type="notification_channel", resource_id=str(channel.channel_id), after_data=self.public_channel(channel))
        self.db.commit()
        return self.public_channel(channel)

    def update_channel(self, user: SysUser, channel_id: int, payload: NotificationChannelUpdate) -> dict:
        require_super_admin(user)
        channel = self.channels.get(channel_id)
        if not channel:
            raise AppError("资源不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        before = self.public_channel(channel)
        updates = payload.model_dump(exclude_unset=True)
        config = updates.pop("config", None)
        for key, value in updates.items():
            setattr(channel, key, value)
        if config is not None:
            channel.config_encrypted = encrypt_secret(json.dumps(config, ensure_ascii=False))
        channel.p0_only = True
        after = self.public_channel(channel)
        write_operation_log(self.db, user, None, operation_type="UPDATE_NOTIFICATION_CHANNEL", resource_type="notification_channel", resource_id=str(channel.channel_id), before_data=before, after_data=after)
        self.db.commit()
        return self.public_channel(channel)

    def test_channel(self, user: SysUser, channel_id: int, payload: NotificationChannelTest) -> dict:
        require_super_admin(user)
        channel = self.channels.get(channel_id)
        if not channel:
            raise AppError("资源不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        try:
            self._send(channel, payload.title, payload.content)
            write_operation_log(self.db, user, None, operation_type="TEST_NOTIFICATION_CHANNEL", resource_type="notification_channel", resource_id=str(channel.channel_id), after_data={"success": True})
            channel.last_test_at = utcnow()
            channel.last_test_result = "测试发送成功"
            self.db.commit()
            return {"success": True, "message": channel.last_test_result}
        except Exception as exc:
            write_operation_log(self.db, user, None, operation_type="TEST_NOTIFICATION_CHANNEL", resource_type="notification_channel", resource_id=str(channel.channel_id), after_data={"success": False, "error": str(exc)[:500]}, status="FAILED", error_message=str(exc)[:1000])
            channel.last_test_at = utcnow()
            channel.last_test_result = f"测试失败：{exc}"
            self.db.commit()
            return {"success": False, "message": channel.last_test_result}

    def raise_event(self, severity: str, alert_type: str, title: str, content: str, fingerprint: str, company_id: int | None = None, project_id: int | None = None) -> SysAlertEvent:
        existing = self.db.scalar(select(SysAlertEvent).where(SysAlertEvent.fingerprint == fingerprint, SysAlertEvent.alert_status.in_(["OPEN", "NOTIFYING", "NOTIFIED", "ACKED"])))
        if existing:
            existing.occurrence_count += 1
            existing.last_seen_at = utcnow()
            self.db.flush()
            return existing
        event = SysAlertEvent(company_id=company_id, project_id=project_id, severity=severity, alert_status="OPEN", alert_type=alert_type, title=title, content=content, fingerprint=fingerprint, notify_after_at=utcnow())
        self.db.add(event)
        self.db.flush()
        return event

    def list_events(self, user: SysUser) -> list[dict]:
        require_super_admin(user)
        rows = list(self.db.scalars(select(SysAlertEvent).order_by(SysAlertEvent.last_seen_at.desc()).limit(500)).all())
        return [{c.name: getattr(item, c.name) for c in item.__table__.columns} for item in rows]

    def ack_event(self, user: SysUser, alert_id: int) -> dict:
        require_super_admin(user)
        event = self.db.get(SysAlertEvent, alert_id)
        if not event:
            raise AppError("资源不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        before = {c.name: getattr(event, c.name) for c in event.__table__.columns}
        if event.alert_status in {"OPEN", "NOTIFIED"}:
            event.alert_status = "ACKED"
        after = {c.name: getattr(event, c.name) for c in event.__table__.columns}
        write_operation_log(self.db, user, None, operation_type="ACK_ALERT", resource_type="alert", resource_id=str(event.alert_id), before_data=before, after_data=after)
        self.db.commit()
        return {c.name: getattr(event, c.name) for c in event.__table__.columns}

    def resolve_event(self, user: SysUser, alert_id: int) -> dict:
        require_super_admin(user)
        event = self.db.get(SysAlertEvent, alert_id)
        if not event:
            raise AppError("资源不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        before = {c.name: getattr(event, c.name) for c in event.__table__.columns}
        event.alert_status = "RESOLVED"
        event.resolved_at = utcnow()
        after = {c.name: getattr(event, c.name) for c in event.__table__.columns}
        write_operation_log(self.db, user, None, operation_type="RESOLVE_ALERT", resource_type="alert", resource_id=str(event.alert_id), before_data=before, after_data=after)
        self.db.commit()
        return {c.name: getattr(event, c.name) for c in event.__table__.columns}

    def process_pending(self, limit: int = 50) -> int:
        events = list(self.db.scalars(select(SysAlertEvent).where(SysAlertEvent.severity == "P0", SysAlertEvent.alert_status.in_(["OPEN", "NOTIFYING", "NOTIFIED"]), (SysAlertEvent.notify_after_at.is_(None)) | (SysAlertEvent.notify_after_at <= utcnow())).order_by(SysAlertEvent.created_at.asc()).limit(limit)).all())
        count = 0
        for event in events:
            channels = self._matched_channels(event)
            if not channels:
                event.alert_status = "SUPPRESSED"
                event.content = (event.content or "") + "\n未配置启用的 P0 通知渠道。"
                count += 1
                continue
            event.alert_status = "NOTIFYING"
            self.db.flush()
            ok_any = False
            for channel in channels:
                delivery = SysAlertDelivery(alert_id=event.alert_id, channel_id=channel.channel_id, delivery_status="PENDING")
                self.db.add(delivery)
                self.db.flush()
                try:
                    self._send(channel, event.title, event.content)
                    delivery.delivery_status = "DELIVERED"
                    delivery.delivered_at = utcnow()
                    ok_any = True
                except Exception as exc:
                    delivery.delivery_status = "FAILED"
                    delivery.attempt_count += 1
                    delivery.last_error = str(exc)[:4000]
            if ok_any:
                event.alert_status = "NOTIFIED"
                event.notified_at = utcnow()
                event.notify_after_at = utcnow() + timedelta(seconds=max((c.cooldown_seconds for c in channels), default=1800))
            else:
                event.alert_status = "OPEN"
                event.notify_after_at = utcnow() + timedelta(minutes=5)
            count += 1
        self.db.commit()
        return count

    def _matched_channels(self, event: SysAlertEvent) -> list[SysNotificationChannel]:
        rows = list(self.db.scalars(select(SysNotificationChannel).where(SysNotificationChannel.channel_status == "ENABLED", SysNotificationChannel.p0_only.is_(True))).all())
        matched = []
        for channel in rows:
            if channel.scope_type == "SYSTEM":
                matched.append(channel)
            elif channel.scope_type == "COMPANY" and channel.company_id == event.company_id:
                matched.append(channel)
            elif channel.scope_type == "PROJECT" and channel.project_id == event.project_id:
                matched.append(channel)
        return matched

    def _config(self, channel: SysNotificationChannel) -> dict[str, Any]:
        if not channel.config_encrypted:
            return {}
        return json.loads(decrypt_secret(channel.config_encrypted))

    def _send(self, channel: SysNotificationChannel, title: str, content: str) -> None:
        config = self._config(channel)
        text = f"【P0】{title}\n{content}"
        if channel.channel_type in {"FEISHU", "WEWORK", "DINGTALK"}:
            webhook = config.get("webhook") or config.get("url")
            if not webhook:
                raise RuntimeError("Webhook 未配置")
            response = requests.post(webhook, json={"msgtype": "text", "text": {"content": text}}, timeout=10)
            if response.status_code < 200 or response.status_code >= 300:
                raise RuntimeError(f"Webhook 返回 HTTP {response.status_code}: {response.text[:500]}")
            return
        if channel.channel_type == "EMAIL":
            host = config.get("smtpHost")
            port = int(config.get("smtpPort") or 465)
            username = config.get("username")
            password = config.get("password")
            receivers = config.get("receivers") or []
            if isinstance(receivers, str):
                receivers = [item.strip() for item in receivers.split(",") if item.strip()]
            if not host or not receivers:
                raise RuntimeError("邮箱 SMTP 或收件人未配置")
            message = EmailMessage()
            message["Subject"] = f"【P0】{title}"
            message["From"] = config.get("from") or username or "crawler-platform@example.local"
            message["To"] = ",".join(receivers)
            message.set_content(content)
            with smtplib.SMTP_SSL(host, port, timeout=10) as smtp:
                if username and password:
                    smtp.login(username, password)
                smtp.send_message(message)
            return
        raise RuntimeError("不支持的通知类型")

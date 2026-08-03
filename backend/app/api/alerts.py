from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SysUser
from app.responses import ok
from app.schemas import NotificationChannelCreate, NotificationChannelTest, NotificationChannelUpdate
from app.services.alert_service import AlertService

channel_router = APIRouter(prefix="/notification-channels", tags=["告警通知"])
alert_router = APIRouter(prefix="/alerts", tags=["告警事件"])


@channel_router.get("")
def list_channels(user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(AlertService(db).list_channels(user))


@channel_router.post("")
def create_channel(payload: NotificationChannelCreate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(AlertService(db).create_channel(user, payload))


@channel_router.patch("/{channel_id}")
def update_channel(channel_id: int, payload: NotificationChannelUpdate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(AlertService(db).update_channel(user, channel_id, payload))


@channel_router.post("/{channel_id}/tests")
def create_channel_test(channel_id: int, payload: NotificationChannelTest, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(AlertService(db).test_channel(user, channel_id, payload))


@alert_router.get("")
def list_alerts(user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(AlertService(db).list_events(user))


@alert_router.patch("/{alert_id}/acknowledgements")
@alert_router.patch("/{alert_id}/acknowledgement")
def update_alert_acknowledgement(alert_id: int, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(AlertService(db).ack_event(user, alert_id))


@alert_router.patch("/{alert_id}/resolutions")
@alert_router.patch("/{alert_id}/resolution")
def update_alert_resolution(alert_id: int, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(AlertService(db).resolve_event(user, alert_id))

"""Audit log API routes."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.config import settings
from app.auth.dependencies import require_admin
from app.models.user import User
from app.models.audit_log import AuditLog

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditLogResponse(BaseModel):
    id: int
    timestamp: str
    user_id: Optional[int] = None
    username: Optional[str] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    model_config = {"from_attributes": True}


@router.get("/", response_model=list[AuditLogResponse])
def list_audit_logs(
    limit: int = Query(default=100, le=500),
    action: Optional[str] = Query(default=None),
    entity_type: Optional[str] = Query(default=None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List audit log entries. Requires ADMIN or SYSTEM role."""
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()

    # Convert timestamps to configured timezone and date format
    from datetime import datetime, timezone as dt_timezone
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(settings.timezone)
    except (ImportError, KeyError, OSError):
        tz = None

    DATE_FMT_MAP = {
        "dd/MM/yyyy": "%d/%m/%Y",
        "MM/dd/yyyy": "%m/%d/%Y",
        "yyyy-MM-dd": "%Y-%m-%d",
        "dd.MM.yyyy": "%d.%m.%Y",
    }
    dt_fmt = DATE_FMT_MAP.get(settings.date_format, "%d/%m/%Y")
    full_fmt = f"{dt_fmt} %H:%M:%S"

    def _fmt_ts(ts: datetime) -> str:
        if not ts:
            return ""
        if tz:
            ts = ts.replace(tzinfo=ts.tzinfo or dt_timezone.utc).astimezone(tz)
        return ts.strftime(full_fmt)

    return [
        AuditLogResponse(
            id=log.id,
            timestamp=_fmt_ts(log.timestamp),
            user_id=log.user_id,
            username=log.username,
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            old_value=log.old_value,
            new_value=log.new_value,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
        )
        for log in logs
    ]

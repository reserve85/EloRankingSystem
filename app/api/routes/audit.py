"""Audit log API routes."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
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

    return [
        AuditLogResponse(
            id=log.id,
            timestamp=log.timestamp.isoformat() if log.timestamp else "",
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
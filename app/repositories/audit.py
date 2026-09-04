"""Audit log repository for database access."""

from typing import Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditLogRepository:
    """Repository for audit log queries."""

    def __init__(self, db: Session):
        self.db = db

    def get_logs(
        self,
        limit: int,
        action: Optional[str] = None,
        entity_type: Optional[str] = None,
    ) -> list[AuditLog]:
        """Return the most recent audit log entries, newest first."""
        query = self.db.query(AuditLog)
        if action:
            query = query.filter(AuditLog.action == action)
        if entity_type:
            query = query.filter(AuditLog.entity_type == entity_type)
        return query.order_by(AuditLog.timestamp.desc()).limit(limit).all()

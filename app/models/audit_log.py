"""Audit log SQLAlchemy model."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditLog(Base):
    """Audit log model for tracking important system actions."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    username: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    action: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    entity_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    entity_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    old_value: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    new_value: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45), nullable=True  # IPv6 max length
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog(id={self.id}, action='{self.action}', "
            f"user_id={self.user_id}, entity_type='{self.entity_type}')>"
        )

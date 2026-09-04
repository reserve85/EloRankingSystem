"""Club settings SQLAlchemy model.

Stores club logo configuration only. Club identity comes exclusively from the
env/config singleton (``settings.club_name``), so no name is stored here. The
old ``club_name`` column was dead weight (write-rarely / never-read) and was
dropped in migration ``d1e2f3a4b5c6`` - the same "environment/config wins"
decision already applied to the Elo knobs in ``f1e2d3c4b5a6``.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ClubSettings(Base):
    """Club settings model for storing club logo configuration."""

    __tablename__ = "club_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    club_logo_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, default=None)
    club_logo_dark_path: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<ClubSettings(id={self.id}, club_logo_path='{self.club_logo_path}')>"

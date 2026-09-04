"""Club settings SQLAlchemy model.

Stores club identity and logo configuration only. Elo parameters
(``default_elo``, ``k_factor``, ``inactivity_months``) are intentionally NOT
stored here: they are read exclusively from the env/config singleton
(``settings.*``), so environment/config wins. The old DB columns were dead
weight and were dropped in migration ``f1e2d3c4b5a6``.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ClubSettings(Base):
    """Club settings model for storing club identity and logo configuration."""

    __tablename__ = "club_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    club_name: Mapped[str] = mapped_column(String(200), nullable=False, default="Dart Club")
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
        return f"<ClubSettings(id={self.id}, club_name='{self.club_name}')>"

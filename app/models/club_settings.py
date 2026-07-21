"""Club settings SQLAlchemy model."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ClubSettings(Base):
    """Club settings model for storing application-wide configuration."""

    __tablename__ = "club_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    club_name: Mapped[str] = mapped_column(
        String(200), nullable=False, default="Dart Club"
    )
    club_logo_path: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, default=None
    )
    default_elo: Mapped[int] = mapped_column(Integer, nullable=False, default=1200)
    k_factor: Mapped[float] = mapped_column(Float, nullable=False, default=32.0)
    inactivity_months: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
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

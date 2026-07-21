"""Player SQLAlchemy model."""

from datetime import datetime, date
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Player(Base):
    """Player model for dart club members."""

    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    start_elo: Mapped[int] = mapped_column(Integer, nullable=False, default=1200)
    current_elo: Mapped[float] = mapped_column(Float, nullable=False, default=1200.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_match_date: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, default=None
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
        return (
            f"<Player(id={self.id}, name='{self.name}', "
            f"current_elo={self.current_elo}, active={self.active})>"
        )
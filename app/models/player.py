"""Player SQLAlchemy model."""

from datetime import datetime, date
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.core.database import Base


class Player(Base):
    """Player model for dart club members."""

    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    # Fix #3: insert defaults are derived from the configured DEFAULT_ELO at
    # flush time instead of hardcoding 1200, so direct ORM inserts (and the
    # service layer) all agree with the admin form.
    start_elo: Mapped[int] = mapped_column(
        Integer, nullable=False, default=lambda: settings.default_elo
    )
    current_elo: Mapped[float] = mapped_column(
        Float, nullable=False, default=lambda: float(settings.default_elo)
    )
    # Fix #3 II: when the player joined the club (member-since date). This is
    # the authoritative "entry date" used by historical rankings: a player is
    # only a competitor from entry_date onwards, and every non-disabled
    # player entered by a date counts on that date (ranked by their Elo as of
    # that date). NULL falls back to the creation date for legacy rows.
    entry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, default=None)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_match_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, default=None)
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

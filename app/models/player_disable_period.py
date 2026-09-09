"""Player disable period SQLAlchemy model.

Records every interval a player was disabled (``disabled_from`` ..
``disabled_to``, with NULL ``disabled_to`` meaning the player is *still*
disabled). The rankings use this history (Fix #5): a player is only excluded
from a ranking on dates inside a recorded disable period - never
retroactively from the beginning. The ``players.disabled`` boolean remains
the current-state flag used for player lists and match selection.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PlayerDisablePeriod(Base):
    """A single \"disabled from X until Y\" interval for a player."""

    __tablename__ = "player_disable_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    disabled_from: Mapped[date] = mapped_column(Date, nullable=False)
    # NULL = the player is still disabled (open interval).
    disabled_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<PlayerDisablePeriod(id={self.id}, player_id={self.player_id}, "
            f"disabled_from={self.disabled_from}, disabled_to={self.disabled_to})>"
        )

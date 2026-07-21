"""Match SQLAlchemy model."""

from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Match(Base):
    """Match model for recording dart game results.

    Best-of-5 format: player scores determine the winner.
    Valid scores: 3:0, 3:1, 3:2, 2:3, 1:3, 0:3
    Winner is the player with score 3.
    """

    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Player references
    player_a_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.id"), nullable=False, index=True
    )
    player_b_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.id"), nullable=False, index=True
    )

    # Best-of-5 scores
    player1_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    player2_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Result (computed from scores)
    winner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.id"), nullable=False
    )
    loser_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.id"), nullable=False
    )

    # Elo tracking - snapshots before match
    elo_before_a: Mapped[float] = mapped_column(Float, nullable=False)
    elo_before_b: Mapped[float] = mapped_column(Float, nullable=False)

    # Elo tracking - snapshots after match
    elo_after_a: Mapped[float] = mapped_column(Float, nullable=False)
    elo_after_b: Mapped[float] = mapped_column(Float, nullable=False)

    # Elo change
    elo_change_a: Mapped[float] = mapped_column(Float, nullable=False)
    elo_change_b: Mapped[float] = mapped_column(Float, nullable=False)

    # Audit fields
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
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

    # Relationships
    player_a = relationship("Player", foreign_keys=[player_a_id])
    player_b = relationship("Player", foreign_keys=[player_b_id])
    winner = relationship("Player", foreign_keys=[winner_id])
    loser = relationship("Player", foreign_keys=[loser_id])

    def __repr__(self) -> str:
        return (
            f"<Match(id={self.id}, date={self.date}, "
            f"player_a_id={self.player_a_id}, player_b_id={self.player_b_id}, "
            f"winner_id={self.winner_id})>"
        )
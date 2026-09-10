"""Ranking schemas for input/output validation."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


def status_suffixes(*, inactive: bool, disabled: bool) -> tuple[str, ...]:
    """Status markers appended to a ranking player name.

    Wording and order mirror the ranking table on the dashboard
    (``app/templates/dashboard.html``): ``(inactive)`` first, then
    ``(disabled)`` - both, either, or neither marker may be present. This is
    the single Python definition every consumer (PDF export, future
    reporters) uses, so it cannot drift from the table.
    """
    return tuple(
        marker
        for flag, marker in (
            (inactive, "(inactive)"),
            (disabled, "(disabled)"),
        )
        if flag
    )


class RankingEntry(BaseModel):
    """Single entry in a ranking table."""

    player_id: int
    player_name: str
    position: int
    elo_rating: float
    elo_change: float
    # None when the player has no previous ranking position (no matches up to
    # to_date) - the UI renders it as '-'. (Fix #1)
    position_change: Optional[int] = None
    disabled: bool = False
    inactive: bool = False
    total_matches: int = 0
    total_180s: int = 0
    high_finishes: list[int] = []
    low_darts: list[int] = []

    model_config = {"from_attributes": True}

    @property
    def display_name(self) -> str:
        """Name exactly as shown in the ranking table, e.g. ``"Alice (disabled)"``.

        The plain :attr:`player_name` is left untouched; status markers are
        appended in :func:`status_suffixes` order.
        """
        suffixes = status_suffixes(inactive=self.inactive, disabled=self.disabled)
        if not suffixes:
            return self.player_name
        return f"{self.player_name} {' '.join(suffixes)}"


class RankingResponse(BaseModel):
    """Response containing ranking data."""

    from_date: date
    to_date: date
    entries: list[RankingEntry]
    generated_at: datetime


class RankingRequest(BaseModel):
    """Request parameters for ranking generation."""

    from_date: Optional[date] = None
    to_date: Optional[date] = None
    include_inactive: bool = False

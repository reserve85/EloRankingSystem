"""Ranking API routes."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.dependencies import require_user
from app.models.user import User
from app.schemas.ranking import RankingResponse
from app.services.ranking import RankingService

router = APIRouter(prefix="/rankings", tags=["rankings"])


@router.get("/", response_model=RankingResponse)
def get_ranking(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    include_inactive: bool = False,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Generate a ranking for the given date range.

    All authenticated users can view rankings.

    Args:
        from_date: Start of period (default: first day of current month).
        to_date: End of period (default: today).
        include_inactive: If True, include inactive players.
    """
    service = RankingService(db)
    return service.generate_ranking(
        from_date=from_date,
        to_date=to_date,
        include_inactive=include_inactive,
    )

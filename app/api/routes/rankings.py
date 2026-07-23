"""Ranking API routes."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.dependencies import require_user
from app.models.user import User
from app.repositories.player import PlayerRepository
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


@router.get("/player-stats/{player_id}")
def get_player_statistics(
    player_id: int,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Get dart statistics for a specific player.

    Returns period and all-time statistics for 180s, high finishes, and low darts.
    All authenticated users can view player statistics.
    """
    player_repo = PlayerRepository(db)
    player = player_repo.get_by_id(player_id)
    if player is None:
        raise HTTPException(status_code=404, detail=f"Player {player_id} not found")

    service = RankingService(db)
    stats = service.get_player_statistics(
        player_id=player_id,
        from_date=from_date,
        to_date=to_date,
    )
    stats["player_name"] = player.name
    return stats


@router.get("/player-stats/{player_id}/elo-history")
def get_elo_history(
    player_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Get Elo history for a player (all matches with Elo after each).

    Returns a list of {date, elo, match_id} entries for charting.
    """
    player_repo = PlayerRepository(db)
    player = player_repo.get_by_id(player_id)
    if player is None:
        raise HTTPException(status_code=404, detail=f"Player {player_id} not found")

    service = RankingService(db)
    history = service.get_elo_history(player_id)
    return {"player_id": player_id, "player_name": player.name, "history": history}


@router.get("/player-stats/{player_id}/ath")
def get_all_time_highs(
    player_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Get All Time High Elo and All Time High Ranking for a player.

    Returns max_elo, date_reached, best_rank, rank_date_reached.
    """
    player_repo = PlayerRepository(db)
    player = player_repo.get_by_id(player_id)
    if player is None:
        raise HTTPException(status_code=404, detail=f"Player {player_id} not found")

    service = RankingService(db)
    ath_elo = service.get_all_time_high_elo(player_id)
    ath_rank = service.get_all_time_high_ranking(player_id)
    return {
        "player_id": player_id,
        "player_name": player.name,
        "ath_elo": ath_elo,
        "ath_rank": ath_rank,
    }

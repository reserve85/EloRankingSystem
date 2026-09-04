"""Match management API routes."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.dependencies import require_admin, require_system, require_user
from app.models.user import User
from app.schemas.match import MatchCreate, MatchUpdate, MatchResponse
from app.services.match import MatchService

router = APIRouter(prefix="/matches", tags=["matches"])


@router.post("/", response_model=MatchResponse, status_code=status.HTTP_201_CREATED)
def create_match(
    data: MatchCreate,
    force: bool = False,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Create a new match. All authenticated users (USER/ADMIN/SYSTEM).

    If force=false (default), returns 409 if a duplicate match exists.
    If force=true, skips the duplicate check and saves anyway.
    """
    service = MatchService(db)
    return service.create_match(
        data, created_by=current_user.id, username=current_user.username, force=force
    )


@router.get("/", response_model=list[MatchResponse])
def list_matches(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """List all matches with optional date range filter."""
    service = MatchService(db)
    return service.get_all_matches(from_date=from_date, to_date=to_date)


@router.post("/recalculate-all")
def recalculate_all(
    current_user: User = Depends(require_system),
    db: Session = Depends(get_db),
):
    """Recalculate the complete Elo timeline from scratch. SYSTEM role only.

    Replays every match chronologically from each player's ``start_elo`` to
    repair any non-canonical Elo snapshots in the database (e.g. after a
    recalculation bugfix deployment). This is a one-time data-repair
    operation and is intentionally restricted to the SYSTEM user, who should
    create a backup before running it.
    """
    service = MatchService(db)
    result = service.recalculate_all(
        user_id=current_user.id,
        username=current_user.username,
    )
    return {
        "detail": (
            f"Full Elo recalculation completed: "
            f"{result['matches_recalculated']} matches recalculated, "
            f"{result['players_affected']} players affected."
        ),
        **result,
    }


@router.get("/{match_id}", response_model=MatchResponse)
def get_match(
    match_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Get a match by ID. All authenticated users."""
    service = MatchService(db)
    return service.get_match(match_id)


@router.put("/{match_id}", response_model=MatchResponse)
def update_match(
    match_id: int,
    data: MatchUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update a match. Requires ADMIN or SYSTEM role."""
    service = MatchService(db)
    return service.update_match(
        match_id, data, updated_by=current_user.id, username=current_user.username
    )


@router.delete("/{match_id}", status_code=status.HTTP_200_OK)
def delete_match(
    match_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete a match. Requires ADMIN or SYSTEM role."""
    service = MatchService(db)
    service.delete_match(match_id, deleted_by=current_user.id, username=current_user.username)
    return {"detail": f"Match {match_id} deleted"}

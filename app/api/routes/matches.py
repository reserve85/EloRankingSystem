"""Match management API routes."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.dependencies import require_admin, require_user
from app.models.user import User
from app.schemas.match import MatchCreate, MatchResponse
from app.services.match import MatchService

router = APIRouter(prefix="/matches", tags=["matches"])


@router.post("/", response_model=MatchResponse, status_code=status.HTTP_201_CREATED)
def create_match(
    data: MatchCreate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Create a new match. All authenticated users (USER/ADMIN/SYSTEM)."""
    service = MatchService(db)
    return service.create_match(data, created_by=current_user.id)


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


@router.get("/{match_id}", response_model=MatchResponse)
def get_match(
    match_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Get a match by ID. All authenticated users."""
    service = MatchService(db)
    return service.get_match(match_id)


@router.delete("/{match_id}", status_code=status.HTTP_200_OK)
def delete_match(
    match_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete a match. Requires ADMIN or SYSTEM role."""
    service = MatchService(db)
    service.delete_match(match_id, deleted_by=current_user.id)
    return {"detail": f"Match {match_id} deleted"}
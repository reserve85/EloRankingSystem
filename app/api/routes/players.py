"""Player management API routes."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.dependencies import require_admin, require_user
from app.models.user import User
from app.schemas.player import PlayerCreate, PlayerUpdate, PlayerResponse
from app.services.player import PlayerService

router = APIRouter(prefix="/players", tags=["players"])


@router.post("/", response_model=PlayerResponse, status_code=status.HTTP_201_CREATED)
def create_player(
    data: PlayerCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new player. Requires ADMIN or SYSTEM role."""
    service = PlayerService(db)
    player = service.create_player(data)
    return player


@router.get("/", response_model=list[PlayerResponse])
def list_players(
    include_disabled: bool = False,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """List all players. All authenticated users can view players."""
    service = PlayerService(db)
    return service.get_all_players(include_disabled=include_disabled)


@router.get("/active", response_model=list[PlayerResponse])
def list_active_players(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """List active, non-disabled players. All authenticated users."""
    service = PlayerService(db)
    return service.get_active_players()


@router.get("/{player_id}", response_model=PlayerResponse)
def get_player(
    player_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Get a player by ID. All authenticated users."""
    service = PlayerService(db)
    return service.get_player(player_id)


@router.put("/{player_id}", response_model=PlayerResponse)
def update_player(
    player_id: int,
    data: PlayerUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update a player. Requires ADMIN or SYSTEM role."""
    service = PlayerService(db)
    return service.update_player(player_id, data)


@router.post("/{player_id}/disable", response_model=PlayerResponse)
def disable_player(
    player_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Disable a player. Requires ADMIN or SYSTEM role."""
    service = PlayerService(db)
    return service.disable_player(player_id)


@router.post("/{player_id}/reactivate", response_model=PlayerResponse)
def reactivate_player(
    player_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Reactivate a disabled player. Requires ADMIN or SYSTEM role."""
    service = PlayerService(db)
    return service.reactivate_player(player_id)
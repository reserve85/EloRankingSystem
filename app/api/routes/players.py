"""Player management API routes."""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.dependencies import require_admin, require_user
from app.models.user import User
from app.schemas.player import PlayerCreate, PlayerUpdate, PlayerResponse
from app.services.player import PlayerService
from app.services.audit import log_event, get_client_info

router = APIRouter(prefix="/players", tags=["players"])


@router.post("/", response_model=PlayerResponse, status_code=status.HTTP_201_CREATED)
def create_player(
    request: Request,
    data: PlayerCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new player. Requires ADMIN or SYSTEM role."""
    service = PlayerService(db)
    player = service.create_player(data)
    ip, ua = get_client_info(request)
    log_event(
        db, action="PLAYER_CREATED", entity_type="player",
        entity_id=player.id, user_id=current_user.id,
        username=current_user.username,
        new_value={"name": player.name, "start_elo": player.start_elo},
        ip_address=ip, user_agent=ua,
    )
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
    request: Request,
    data: PlayerUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update a player. Requires ADMIN or SYSTEM role."""
    service = PlayerService(db)
    player = service.get_player(player_id)
    old = {"name": player.name, "start_elo": player.start_elo}
    player = service.update_player(player_id, data)
    ip, ua = get_client_info(request)
    log_event(
        db, action="PLAYER_UPDATED", entity_type="player",
        entity_id=player.id, user_id=current_user.id,
        username=current_user.username,
        old_value=old,
        new_value={"name": player.name, "start_elo": player.start_elo},
        ip_address=ip, user_agent=ua,
    )
    return player


@router.post("/{player_id}/disable", response_model=PlayerResponse)
def disable_player(
    player_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Disable a player. Requires ADMIN or SYSTEM role."""
    service = PlayerService(db)
    player = service.disable_player(player_id)
    ip, ua = get_client_info(request)
    log_event(
        db, action="PLAYER_DISABLED", entity_type="player",
        entity_id=player.id, user_id=current_user.id,
        username=current_user.username,
        ip_address=ip, user_agent=ua,
    )
    return player


@router.post("/{player_id}/reactivate", response_model=PlayerResponse)
def reactivate_player(
    player_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Reactivate a disabled player. Requires ADMIN or SYSTEM role."""
    service = PlayerService(db)
    player = service.reactivate_player(player_id)
    ip, ua = get_client_info(request)
    log_event(
        db, action="PLAYER_REACTIVATED", entity_type="player",
        entity_id=player.id, user_id=current_user.id,
        username=current_user.username,
        ip_address=ip, user_agent=ua,
    )
    return player

"""Club settings API routes."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.dependencies import require_admin
from app.models.user import User
from app.models.club_settings import ClubSettings
from app.services.audit import log_event, get_client_info
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    club_name: Optional[str] = None
    default_elo: Optional[int] = None
    k_factor: Optional[float] = None
    inactivity_months: Optional[int] = None


class SettingsResponse(BaseModel):
    id: int
    club_name: str
    default_elo: int
    k_factor: float
    inactivity_months: int

    model_config = {"from_attributes": True}


@router.get("/", response_model=SettingsResponse)
def get_settings(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Get club settings. Requires ADMIN or SYSTEM role."""
    settings = db.query(ClubSettings).first()
    if settings is None:
        settings = ClubSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.put("/", response_model=SettingsResponse)
def update_settings(request: Request, data: SettingsUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Update club settings. Requires ADMIN or SYSTEM role."""
    settings = db.query(ClubSettings).first()
    if settings is None:
        settings = ClubSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)

    old = {
        "club_name": settings.club_name,
        "default_elo": settings.default_elo,
        "k_factor": settings.k_factor,
        "inactivity_months": settings.inactivity_months,
    }

    if data.club_name is not None:
        settings.club_name = data.club_name
    if data.default_elo is not None:
        settings.default_elo = data.default_elo
    if data.k_factor is not None:
        settings.k_factor = data.k_factor
    if data.inactivity_months is not None:
        settings.inactivity_months = data.inactivity_months
    db.commit()
    db.refresh(settings)

    new = {
        "club_name": settings.club_name,
        "default_elo": settings.default_elo,
        "k_factor": settings.k_factor,
        "inactivity_months": settings.inactivity_months,
    }

    ip, ua = get_client_info(request)
    log_event(
        db, action="CLUB_SETTINGS_CHANGED", entity_type="club_settings",
        entity_id=settings.id, user_id=current_user.id, username=current_user.username,
        old_value=old, new_value=new,
        ip_address=ip, user_agent=ua,
    )
    return settings

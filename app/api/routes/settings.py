"""Club settings API routes."""

import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse
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
    club_logo_path: Optional[str] = None

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


@router.post("/logo", response_model=SettingsResponse)
async def upload_logo(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Upload club logo. Requires ADMIN or SYSTEM role."""
    ip, ua = get_client_info(request)

    # Validate file extension
    allowed_extensions = {".png", ".svg", ".jpg", ".jpeg"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Invalid file type '{ext}'. Allowed: {', '.join(allowed_extensions)}")

    # Validate MIME type
    allowed_mimes = {"image/png", "image/svg+xml", "image/jpeg", "image/jpg"}
    if file.content_type not in allowed_mimes:
        raise HTTPException(status_code=400, detail=f"Invalid content type '{file.content_type}'")

    # Read and validate size (max 2MB)
    content = await file.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size: 2MB")

    # Save file
    upload_dir = os.path.join("uploads")
    os.makedirs(upload_dir, exist_ok=True)
    safe_name = f"club_logo_{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(upload_dir, safe_name)

    # Delete old logo if exists
    settings = db.query(ClubSettings).first()
    if settings is None:
        settings = ClubSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)

    if settings.club_logo_path and os.path.exists(settings.club_logo_path):
        try:
            os.remove(settings.club_logo_path)
        except OSError:
            pass

    with open(file_path, "wb") as f:
        f.write(content)

    old_path = settings.club_logo_path
    settings.club_logo_path = file_path
    db.commit()
    db.refresh(settings)

    log_event(
        db, action="CLUB_LOGO_UPLOADED", entity_type="club_settings",
        entity_id=settings.id, user_id=current_user.id, username=current_user.username,
        old_value={"club_logo_path": old_path}, new_value={"club_logo_path": file_path},
        ip_address=ip, user_agent=ua,
    )

    return settings


@router.get("/logo")
def get_logo(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Download the club logo. Requires authentication."""
    settings = db.query(ClubSettings).first()
    if settings is None or not settings.club_logo_path or not os.path.exists(settings.club_logo_path):
        raise HTTPException(status_code=404, detail="No logo uploaded")

    return FileResponse(settings.club_logo_path, media_type="image/*")


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

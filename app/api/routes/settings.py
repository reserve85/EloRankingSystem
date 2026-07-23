"""Club settings API routes."""

import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.auth.dependencies import require_admin, get_optional_user
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
    cs = db.query(ClubSettings).first()
    if cs is None:
        cs = ClubSettings()
        db.add(cs)
        db.commit()
        db.refresh(cs)
    return cs


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

    # Save file to configured upload directory
    upload_dir = settings.upload_dir
    os.makedirs(upload_dir, exist_ok=True)
    safe_name = f"club_logo_{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(upload_dir, safe_name)

    # Delete old logo if exists
    cs = db.query(ClubSettings).first()
    if cs is None:
        cs = ClubSettings()
        db.add(cs)
        db.commit()
        db.refresh(cs)

    if cs.club_logo_path and os.path.exists(cs.club_logo_path):
        try:
            os.remove(cs.club_logo_path)
        except OSError:
            pass

    with open(file_path, "wb") as f:
        f.write(content)

    old_path = cs.club_logo_path
    cs.club_logo_path = file_path
    db.commit()
    db.refresh(cs)

    log_event(
        db, action="CLUB_LOGO_UPLOADED", entity_type="club_settings",
        entity_id=cs.id, user_id=current_user.id, username=current_user.username,
        old_value={"club_logo_path": old_path}, new_value={"club_logo_path": file_path},
        ip_address=ip, user_agent=ua,
    )

    return cs


@router.get("/logo")
def get_logo(current_user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    """Download the club logo. Publicly accessible."""
    cs = db.query(ClubSettings).first()
    if cs is None or not cs.club_logo_path or not os.path.exists(cs.club_logo_path):
        raise HTTPException(status_code=404, detail="No logo uploaded")

    return FileResponse(cs.club_logo_path, media_type="image/*")


@router.put("/", response_model=SettingsResponse)
def update_settings(request: Request, data: SettingsUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Update club settings. Requires ADMIN or SYSTEM role."""
    cs = db.query(ClubSettings).first()
    if cs is None:
        cs = ClubSettings()
        db.add(cs)
        db.commit()
        db.refresh(cs)

    old = {
        "club_name": cs.club_name,
        "default_elo": cs.default_elo,
        "k_factor": cs.k_factor,
        "inactivity_months": cs.inactivity_months,
    }

    if data.club_name is not None:
        cs.club_name = data.club_name
    if data.default_elo is not None:
        cs.default_elo = data.default_elo
    if data.k_factor is not None:
        cs.k_factor = data.k_factor
    if data.inactivity_months is not None:
        cs.inactivity_months = data.inactivity_months
    db.commit()
    db.refresh(cs)

    new = {
        "club_name": cs.club_name,
        "default_elo": cs.default_elo,
        "k_factor": cs.k_factor,
        "inactivity_months": cs.inactivity_months,
    }

    ip, ua = get_client_info(request)
    log_event(
        db, action="CLUB_SETTINGS_CHANGED", entity_type="club_settings",
        entity_id=cs.id, user_id=current_user.id, username=current_user.username,
        old_value=old, new_value=new,
        ip_address=ip, user_agent=ua,
    )
    return cs

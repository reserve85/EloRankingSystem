"""Club settings API routes."""

import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
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
    # Override club_name from env/config, not from DB
    cs.club_name = settings.club_name or settings.app_name
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

    # Override club_name from env/config
    cs.club_name = settings.club_name or settings.app_name
    return cs


class QRCodeRequest(BaseModel):
    username: str
    password: str


@router.post("/qrcode")
def generate_qrcode(
    request: Request,
    data: QRCodeRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Generate QR code for auto-login URL. Only USER role accounts allowed."""
    import io
    from app.auth.password import verify_password
    from app.models.user import UserRole

    # Find the target user
    target_user = db.query(User).filter(User.username == data.username).first()
    if target_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Only USER role allowed for QR code
    if target_user.role != UserRole.USER:
        raise HTTPException(status_code=403, detail="QR code can only be generated for USER role accounts, not ADMIN or SYSTEM")

    if not target_user.active:
        raise HTTPException(status_code=400, detail="User account is disabled")

    # Verify password
    if not verify_password(data.password, target_user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid password")

    # Generate QR code
    import qrcode

    base_url = str(request.base_url).rstrip("/")
    url = f"{base_url}/auth/auto-login?u={data.username}&p={data.password}"

    # 10x10cm at 72 DPI ≈ 283px, use box_size=10, border=2 for clean output
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


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
        "default_elo": cs.default_elo,
        "k_factor": cs.k_factor,
        "inactivity_months": cs.inactivity_months,
    }

    if data.default_elo is not None:
        cs.default_elo = data.default_elo
    if data.k_factor is not None:
        cs.k_factor = data.k_factor
    if data.inactivity_months is not None:
        cs.inactivity_months = data.inactivity_months
    db.commit()
    db.refresh(cs)

    new = {
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
    # Override club_name from env/config
    cs.club_name = settings.club_name or settings.app_name
    return cs

"""Club settings API routes."""

import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
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
    club_logo_dark_path: Optional[str] = None

    model_config = {"from_attributes": True}


def _validate_logo_upload(file: UploadFile, content: bytes) -> None:
    """Validate logo file extension, MIME type, and size."""
    allowed_extensions = {".png", ".svg", ".jpg", ".jpeg"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Invalid file type '{ext}'. Allowed: {', '.join(allowed_extensions)}")

    allowed_mimes = {"image/png", "image/svg+xml", "image/jpeg", "image/jpg"}
    if file.content_type not in allowed_mimes:
        raise HTTPException(status_code=400, detail=f"Invalid content type '{file.content_type}'")

    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size: 2MB")


def _save_logo_file(file: UploadFile, content: bytes, prefix: str, upload_dir: str) -> str:
    """Save logo file and return the file path."""
    os.makedirs(upload_dir, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1].lower()
    safe_name = f"{prefix}_{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(upload_dir, safe_name)
    with open(file_path, "wb") as f:
        f.write(content)
    return file_path


def _get_or_create_settings(db: Session) -> ClubSettings:
    """Get or create the club settings row."""
    cs = db.query(ClubSettings).first()
    if cs is None:
        cs = ClubSettings()
        db.add(cs)
        db.commit()
        db.refresh(cs)
    return cs


def _delete_logo_file(path: str) -> None:
    """Safely delete a logo file."""
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


@router.get("/", response_model=SettingsResponse)
def get_settings(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Get club settings. Requires ADMIN or SYSTEM role."""
    cs = _get_or_create_settings(db)
    # Override club_name from env/config, not from DB
    cs.club_name = settings.club_name or settings.app_name
    return cs


@router.post("/logo", response_model=SettingsResponse)
async def upload_logo(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Query(default="light", pattern="^(light|dark)$"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Upload club logo for normal (light) or dark mode. Requires ADMIN or SYSTEM role.

    Args:
        mode: 'light' for normal mode logo, 'dark' for dark mode logo.
    """
    ip, ua = get_client_info(request)
    content = await file.read()
    _validate_logo_upload(file, content)

    cs = _get_or_create_settings(db)

    if mode == "dark":
        _delete_logo_file(cs.club_logo_dark_path)
        file_path = _save_logo_file(file, content, "club_logo_dark", settings.upload_dir)
        old_path = cs.club_logo_dark_path
        cs.club_logo_dark_path = file_path
    else:
        _delete_logo_file(cs.club_logo_path)
        file_path = _save_logo_file(file, content, "club_logo", settings.upload_dir)
        old_path = cs.club_logo_path
        cs.club_logo_path = file_path

    db.commit()
    db.refresh(cs)

    log_event(
        db, action="CLUB_LOGO_UPLOADED", entity_type="club_settings",
        entity_id=cs.id, user_id=current_user.id, username=current_user.username,
        old_value={f"club_logo_{mode}_path": old_path}, new_value={f"club_logo_{mode}_path": file_path},
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
    if not verify_password(target_user.password_hash, data.password):
        raise HTTPException(status_code=401, detail="Invalid password")

    # Generate QR code
    import qrcode

    if settings.app_base_url:
        base_url = settings.app_base_url.rstrip("/")
    else:
        # Respect reverse proxy headers (X-Forwarded-Proto, X-Forwarded-Host)
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host", request.headers.get("host", str(request.base_url).rstrip("/")))
        base_url = f"{scheme}://{host}".rstrip("/")
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


def _get_media_type(file_path: str) -> str:
    """Determine the correct media type from file extension."""
    ext = os.path.splitext(file_path)[1].lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
    }
    return mime_map.get(ext, "image/png")


@router.get("/logo")
def get_logo(
    mode: str = Query(default="light", pattern="^(light|dark)$"),
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Download the club logo. Publicly accessible. Supports mode=light|dark."""
    cs = db.query(ClubSettings).first()
    if cs is None:
        raise HTTPException(status_code=404, detail="No logo uploaded")

    if mode == "dark" and cs.club_logo_dark_path and os.path.exists(cs.club_logo_dark_path):
        return FileResponse(cs.club_logo_dark_path, media_type=_get_media_type(cs.club_logo_dark_path))

    if cs.club_logo_path and os.path.exists(cs.club_logo_path):
        return FileResponse(cs.club_logo_path, media_type=_get_media_type(cs.club_logo_path))

    raise HTTPException(status_code=404, detail="No logo uploaded")


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

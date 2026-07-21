"""Backup and restore API routes."""

import zipfile
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.dependencies import require_admin
from app.models.user import User
from app.services.backup import create_backup, list_backups, restore_backup, get_backup_download
from app.services.audit import log_event, get_client_info

router = APIRouter(prefix="/backup", tags=["backup"])


@router.post("/create")
def create_backup_endpoint(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a backup and return it for download. Requires ADMIN or SYSTEM role."""
    try:
        filename, zip_bytes = create_backup()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    ip, ua = get_client_info(request)
    log_event(
        db, action="BACKUP_CREATED", entity_type="backup",
        user_id=current_user.id, username=current_user.username,
        new_value={"filename": filename},
        ip_address=ip, user_agent=ua,
    )

    return StreamingResponse(
        BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/list")
def list_backups_endpoint(
    current_user: User = Depends(require_admin),
):
    """List available backups. Requires ADMIN or SYSTEM role."""
    return list_backups()


@router.get("/download/{filename}")
def download_backup(
    filename: str,
    current_user: User = Depends(require_admin),
):
    """Download a backup file. Requires ADMIN or SYSTEM role."""
    try:
        content = get_backup_download(filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if content is None:
        raise HTTPException(status_code=404, detail=f"Backup '{filename}' not found")

    return StreamingResponse(
        BytesIO(content),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/restore")
async def restore_backup_endpoint(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Restore from a backup file. Requires ADMIN or SYSTEM role.

    The uploaded file must be a valid backup ZIP created by this system.
    A confirmation is required by sending the file via multipart form.
    """
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Invalid file: must be a .zip backup file")

    content = await file.read()

    try:
        result = restore_backup(content)
    except (ValueError, zipfile.BadZipFile) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")

    ip, ua = get_client_info(request)
    log_event(
        db, action="BACKUP_RESTORED", entity_type="backup",
        user_id=current_user.id, username=current_user.username,
        new_value={
            "filename": file.filename,
            "database_restored": result["database_restored"],
            "pre_restore_backup": result.get("pre_restore_backup"),
        },
        ip_address=ip, user_agent=ua,
    )

    return {
        "message": "Backup restored successfully",
        "details": result,
    }
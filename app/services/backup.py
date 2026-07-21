"""Backup and restore service."""

import os
import shutil
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional

from app.core.config import settings


def _sanitize_path(path: str) -> Path:
    """Sanitize a file path to prevent path traversal attacks.

    Args:
        path: The path to sanitize.

    Returns:
        Sanitized Path object.

    Raises:
        ValueError: If path contains traversal components.
    """
    p = Path(path)
    # Reject any path with .. components
    if ".." in p.parts:
        raise ValueError(f"Invalid path: {path}")
    return p


def get_backup_dir() -> Path:
    """Get the backup directory, creating it if needed."""
    backup_dir = Path(settings.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def create_backup() -> tuple[str, bytes]:
    """Create a backup archive containing database, uploads, and config.

    Returns:
        Tuple of (filename, zip_bytes).

    Raises:
        FileNotFoundError: If database file doesn't exist.
    """
    db_path = Path(settings.data_dir) / "database.db"
    upload_dir = Path(settings.upload_dir)

    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{timestamp}.zip"

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add database
        zf.write(db_path, "database.db")

        # Add uploads if they exist
        if upload_dir.exists():
            for file_path in upload_dir.rglob("*"):
                if file_path.is_file():
                    arcname = f"uploads/{file_path.relative_to(upload_dir)}"
                    zf.write(file_path, arcname)

        # Add metadata
        metadata = (
            f"Elo Ranking System Backup\n"
            f"Created: {datetime.now(timezone.utc).isoformat()}\n"
            f"Version: 0.1.0\n"
        )
        zf.writestr("backup_metadata.txt", metadata)

    # Save a copy to the backup directory
    backup_dir = get_backup_dir()
    backup_file = backup_dir / filename
    with open(backup_file, "wb") as f:
        f.write(buffer.getvalue())

    return filename, buffer.getvalue()


def list_backups() -> list[dict]:
    """List available backup files.

    Returns:
        List of dicts with filename, size, and created_at.
    """
    backup_dir = get_backup_dir()
    backups = []

    if backup_dir.exists():
        for f in sorted(backup_dir.glob("backup_*.zip"), reverse=True):
            stat = f.stat()
            backups.append({
                "filename": f.name,
                "size": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            })

    return backups


def restore_backup(zip_bytes: bytes) -> dict:
    """Restore from a backup archive.

    Args:
        zip_bytes: The backup ZIP file content.

    Returns:
        Dict with restore details.

    Raises:
        ValueError: If backup is invalid or contains unsafe paths.
    """
    db_path = Path(settings.data_dir) / "database.db"
    upload_dir = Path(settings.upload_dir)

    # Validate the ZIP first
    with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
        # Check for path traversal in filenames
        for name in zf.namelist():
            _sanitize_path(name)

        # Verify it contains a database
        if "database.db" not in zf.namelist():
            raise ValueError("Invalid backup: missing database.db")

    # Create a pre-restore backup of current state
    pre_restore_backup = None
    if db_path.exists():
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        pre_restore_name = f"pre_restore_{timestamp}.zip"
        pre_restore_buffer = BytesIO()
        with zipfile.ZipFile(pre_restore_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(db_path, "database.db")
            if upload_dir.exists():
                for file_path in upload_dir.rglob("*"):
                    if file_path.is_file():
                        arcname = f"uploads/{file_path.relative_to(upload_dir)}"
                        zf.write(file_path, arcname)
        backup_dir = get_backup_dir()
        pre_restore_backup = backup_dir / pre_restore_name
        with open(pre_restore_backup, "wb") as f:
            f.write(pre_restore_buffer.getvalue())

    # Perform restore
    with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
        # Restore database
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with zf.open("database.db") as src, open(db_path, "wb") as dst:
            shutil.copyfileobj(src, dst)

        # Restore uploads
        for name in zf.namelist():
            if name.startswith("uploads/") and name != "uploads/":
                target = upload_dir / name[len("uploads/"):]
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)

    return {
        "restored": True,
        "database_restored": True,
        "pre_restore_backup": str(pre_restore_backup) if pre_restore_backup else None,
    }


def get_backup_download(filename: str) -> Optional[bytes]:
    """Get backup file content for download.

    Args:
        filename: The backup filename.

    Returns:
        File content as bytes, or None if not found.

    Raises:
        ValueError: If filename contains path traversal.
    """
    _sanitize_path(filename)

    backup_dir = get_backup_dir()
    backup_file = backup_dir / filename

    if not backup_file.exists() or not backup_file.is_file():
        return None

    # Ensure the file is actually inside the backup directory
    try:
        backup_file.resolve().relative_to(backup_dir.resolve())
    except ValueError:
        raise ValueError("Invalid backup file path")

    with open(backup_file, "rb") as f:
        return f.read()
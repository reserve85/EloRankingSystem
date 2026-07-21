"""Tests for backup and restore."""

import io
import zipfile
from datetime import datetime, timezone

import pytest

from app.models.user import User, UserRole
from app.models.audit_log import AuditLog
from app.auth.password import hash_password
from app.services.backup import _sanitize_path, create_backup, get_backup_download


def _login_as(client, db_session, username, password, role):
    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    client.post("/auth/login", data={"username": username, "password": password})
    return user


class TestPathSanitization:
    """Tests for path traversal protection."""

    def test_normal_path_accepted(self):
        """Normal path should be accepted."""
        result = _sanitize_path("backup_20250101_120000.zip")
        assert result.name == "backup_20250101_120000.zip"

    def test_dot_dot_rejected(self):
        """Path with .. should be rejected."""
        with pytest.raises(ValueError, match="Invalid path"):
            _sanitize_path("../../etc/passwd")

    def test_nested_dot_dot_rejected(self):
        """Path with nested .. should be rejected."""
        with pytest.raises(ValueError, match="Invalid path"):
            _sanitize_path("backups/../../../etc/passwd")

    def test_simple_filename_accepted(self):
        """Simple filename should be accepted."""
        result = _sanitize_path("backup.zip")
        assert result.name == "backup.zip"


class TestBackupCreation:
    """Tests for backup creation."""

    def test_create_backup_returns_zip(self, client, db_session):
        """Creating backup should return a valid ZIP file."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        resp = client.post("/backup/create")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert "backup_" in resp.headers.get("content-disposition", "")
        assert resp.content[:2] == b"PK"  # ZIP magic bytes

    def test_backup_contains_database(self, client, db_session):
        """Backup ZIP should contain the database file."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        resp = client.post("/backup/create")
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = zf.namelist()
        assert "database.db" in names

    def test_backup_contains_metadata(self, client, db_session):
        """Backup ZIP should contain metadata file."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        resp = client.post("/backup/create")
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        assert "backup_metadata.txt" in zf.namelist()

        metadata = zf.read("backup_metadata.txt").decode("utf-8")
        assert "Elo Ranking System" in metadata

    def test_admin_can_create_backup(self, client, db_session):
        """ADMIN should be able to create a backup."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        resp = client.post("/backup/create")
        assert resp.status_code == 200

    def test_system_can_create_backup(self, client, db_session):
        """SYSTEM should be able to create a backup."""
        _login_as(client, db_session, "sys", "pass", UserRole.SYSTEM)

        resp = client.post("/backup/create")
        assert resp.status_code == 200

    def test_user_cannot_create_backup(self, client, db_session):
        """USER should NOT be able to create a backup (403)."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)

        resp = client.post("/backup/create")
        assert resp.status_code == 403

    def test_unauthenticated_cannot_create_backup(self, client, db_session):
        """Unauthenticated request should return 401."""
        resp = client.post("/backup/create")
        assert resp.status_code == 401


class TestBackupAudit:
    """Tests for backup audit logging."""

    def test_backup_create_logged(self, client, db_session):
        """Creating a backup should create BACKUP_CREATED audit entry."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        client.post("/backup/create")

        logs = db_session.query(AuditLog).filter(
            AuditLog.action == "BACKUP_CREATED"
        ).all()
        assert len(logs) >= 1
        log = logs[-1]
        assert log.entity_type == "backup"
        assert log.new_value is not None


class TestBackupList:
    """Tests for listing backups."""

    def test_list_backups_empty(self, client, db_session):
        """Listing backups should return a list."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        resp = client.get("/backup/list")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_backups_after_create(self, client, db_session):
        """After creating a backup, list should contain it."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        client.post("/backup/create")

        resp = client.get("/backup/list")
        backups = resp.json()
        assert len(backups) >= 1
        assert "filename" in backups[0]
        assert "size" in backups[0]

    def test_user_cannot_list_backups(self, client, db_session):
        """USER should not be able to list backups."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)

        resp = client.get("/backup/list")
        assert resp.status_code == 403


class TestBackupDownload:
    """Tests for downloading existing backups."""

    def test_download_backup(self, client, db_session):
        """Should be able to download a previously created backup."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        # Create a backup first
        create_resp = client.post("/backup/create")
        content_disp = create_resp.headers.get("content-disposition", "")
        filename = content_disp.split("filename=")[-1].strip('"')

        # Download it
        resp = client.get(f"/backup/download/{filename}")
        assert resp.status_code == 200
        assert resp.content[:2] == b"PK"

    def test_download_nonexistent_backup(self, client, db_session):
        """Downloading non-existent backup should return 404."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        resp = client.get("/backup/download/nonexistent.zip")
        assert resp.status_code == 404

    def test_download_path_traversal_blocked(self, client, db_session):
        """Path traversal in download should be blocked."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        resp = client.get("/backup/download/../../etc/passwd")
        assert resp.status_code in (400, 404, 422)

    def test_user_cannot_download_backup(self, client, db_session):
        """USER should not be able to download backups."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)

        resp = client.get("/backup/download/somefile.zip")
        assert resp.status_code == 403


class TestBackupRestore:
    """Tests for backup restoration."""

    def test_restore_valid_backup(self, client, db_session):
        """Should be able to restore a valid backup."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        # Create a backup
        create_resp = client.post("/backup/create")
        backup_bytes = create_resp.content

        # Restore it
        resp = client.post(
            "/backup/restore",
            files={"file": ("backup.zip", io.BytesIO(backup_bytes), "application/zip")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Backup restored successfully"
        assert data["details"]["restored"] is True
        assert data["details"]["database_restored"] is True

    def test_restore_invalid_file(self, client, db_session):
        """Restoring invalid file should return 400."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        resp = client.post(
            "/backup/restore",
            files={"file": ("backup.txt", io.BytesIO(b"not a zip"), "application/octet-stream")},
        )
        assert resp.status_code == 400

    def test_restore_non_zip_file(self, client, db_session):
        """Restoring a non-zip file should fail."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        resp = client.post(
            "/backup/restore",
            files={"file": ("backup.zip", io.BytesIO(b"not a valid zip"), "application/zip")},
        )
        assert resp.status_code == 400

    def test_restore_creates_audit_log(self, client, db_session):
        """Restoring should create BACKUP_RESTORED audit entry."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        create_resp = client.post("/backup/create")
        backup_bytes = create_resp.content

        client.post(
            "/backup/restore",
            files={"file": ("backup.zip", io.BytesIO(backup_bytes), "application/zip")},
        )

        logs = db_session.query(AuditLog).filter(
            AuditLog.action == "BACKUP_RESTORED"
        ).all()
        assert len(logs) >= 1
        assert logs[-1].entity_type == "backup"

    def test_user_cannot_restore(self, client, db_session):
        """USER should not be able to restore backups."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)

        resp = client.post(
            "/backup/restore",
            files={"file": ("backup.zip", io.BytesIO(b"PKtest"), "application/zip")},
        )
        assert resp.status_code == 403

    def test_unauthenticated_cannot_restore(self, client, db_session):
        """Unauthenticated request should return 401."""
        resp = client.post(
            "/backup/restore",
            files={"file": ("backup.zip", io.BytesIO(b"PKtest"), "application/zip")},
        )
        assert resp.status_code == 401

    def test_restore_creates_pre_restore_backup(self, client, db_session):
        """Restore should create a pre-restore backup of current state."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        create_resp = client.post("/backup/create")
        backup_bytes = create_resp.content

        resp = client.post(
            "/backup/restore",
            files={"file": ("backup.zip", io.BytesIO(backup_bytes), "application/zip")},
        )
        data = resp.json()
        assert data["details"]["pre_restore_backup"] is not None
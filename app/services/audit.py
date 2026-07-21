"""Audit logging service - centralized audit event recording."""

import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def log_event(
    db: Session,
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    old_value: Optional[Any] = None,
    new_value: Optional[Any] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditLog:
    """Create an audit log entry.

    Args:
        db: Database session.
        action: The action performed (e.g. MATCH_CREATED).
        entity_type: Type of entity affected (e.g. match, player, user).
        entity_id: ID of the affected entity.
        user_id: ID of the user performing the action.
        username: Username of the user performing the action.
        old_value: Previous value (JSON serializable).
        new_value: New value (JSON serializable).
        ip_address: Client IP address.
        user_agent: Client user agent string.

    Returns:
        The created AuditLog entry.
    """
    # Serialize values to JSON strings, never log passwords/secrets
    old_str = _safe_serialize(old_value)
    new_str = _safe_serialize(new_value)

    # Redact sensitive fields
    old_str = _redact_secrets(old_str)
    new_str = _redact_secrets(new_str)

    audit = AuditLog(
        user_id=user_id,
        username=username,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_str,
        new_value=new_str,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(audit)
    db.commit()
    return audit


def _safe_serialize(value: Any) -> Optional[str]:
    """Safely serialize a value to JSON string."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)


def _redact_secrets(value: Optional[str]) -> Optional[str]:
    """Redact passwords and secrets from audit log values."""
    if value is None:
        return None

    sensitive_keys = [
        "password", "password_hash", "secret", "token",
        "jwt_secret", "jwt", "access_token", "authorization",
    ]

    try:
        data = json.loads(value)
        if isinstance(data, dict):
            for key in list(data.keys()):
                if any(s in key.lower() for s in sensitive_keys):
                    data[key] = "[REDACTED]"
            return json.dumps(data, default=str)
    except (json.JSONDecodeError, TypeError):
        pass

    return value


def get_client_info(request) -> tuple[Optional[str], Optional[str]]:
    """Extract IP address and user agent from a request.

    Args:
        request: FastAPI Request object.

    Returns:
        Tuple of (ip_address, user_agent).
    """
    ip = None
    ua = None
    if request:
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent", None)
    return ip, ua

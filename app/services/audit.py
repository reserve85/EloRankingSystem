"""Audit logging service - centralized audit event recording."""

import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.request import get_client_ip
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
    # Fix L7: the caller owns the transaction boundary, so this helper does
    # NOT commit. This keeps an audit event atomic with the business write it
    # accompanies. Flush (autoflush is off) so any constraint error surfaces
    # here and the pending row is visible within the current transaction.
    db.flush()
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


SENSITIVE_KEYS: list[str] = [
    "password", "password_hash", "secret", "token",
    "jwt_secret", "jwt", "access_token", "authorization",
]


def _redact_node(node: Any, sensitive_keys: list[str]) -> Any:
    """Recursively walk dicts and lists, replacing values under sensitive keys."""

    if isinstance(node, dict):
        return {
            key: "[REDACTED]"
            if any(s in str(key.lower()) for s in sensitive_keys)
            else _redact_node(value, sensitive_keys)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_redact_node(item, sensitive_keys) for item in node]
    return node


def _redact_secrets(value: Optional[str]) -> Optional[str]:
    """Redact passwords and secrets from audit log values (recursive; Fix #9)."""

    if value is None:
        return None

    try:
        data = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value

    if isinstance(data, (dict, list)):
        return json.dumps(_redact_node(data, SENSITIVE_KEYS), default=str)
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
        # Fix M6: honor X-Forwarded-For when a trusted reverse proxy is
        # configured, otherwise fall back to the socket peer.
        ip = get_client_ip(request)
        ua = request.headers.get("user-agent", None)
    return ip, ua

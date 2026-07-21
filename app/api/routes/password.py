"""Password management API routes."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.dependencies import get_current_user, require_admin
from app.auth.password import hash_password, verify_password
from app.auth.password_validation import validate_password_strength
from app.models.user import User, UserRole
from app.schemas.password import PasswordChangeRequest, PasswordResetRequest, PasswordResponse
from app.services.audit import log_event, get_client_info

router = APIRouter(prefix="/password", tags=["password"])


@router.post("/change", response_model=PasswordResponse)
def change_own_password(
    request: Request,
    data: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the authenticated user's own password."""
    ip, ua = get_client_info(request)

    if data.new_password != data.confirm_new_password:
        return PasswordResponse(
            success=False,
            message="Passwords do not match",
            errors=["new_password and confirm_new_password must be identical"],
        )

    if not verify_password(current_user.password_hash, data.current_password):
        return PasswordResponse(
            success=False,
            message="Current password is incorrect",
            errors=["current_password does not match"],
        )

    if data.new_password == data.current_password:
        return PasswordResponse(
            success=False,
            message="New password must differ from current password",
            errors=["new_password must not equal current_password"],
        )

    strength_errors = validate_password_strength(data.new_password)
    if strength_errors:
        return PasswordResponse(
            success=False,
            message="Password does not meet security requirements",
            errors=strength_errors,
        )

    current_user.password_hash = hash_password(data.new_password)
    db.commit()

    log_event(
        db, action="PASSWORD_CHANGED", entity_type="user",
        entity_id=current_user.id, user_id=current_user.id,
        username=current_user.username,
        ip_address=ip, user_agent=ua,
    )

    return PasswordResponse(success=True, message="Password changed successfully")


@router.post("/reset", response_model=PasswordResponse)
def reset_user_password(
    request: Request,
    data: PasswordResetRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Reset a user's password. Requires ADMIN or SYSTEM role."""
    ip, ua = get_client_info(request)

    target_user = db.query(User).filter(User.id == data.user_id).first()
    if target_user is None:
        return PasswordResponse(
            success=False,
            message="User not found",
            errors=[f"User with id {data.user_id} does not exist"],
        )

    if target_user.role == UserRole.SYSTEM and current_user.role != UserRole.SYSTEM:
        return PasswordResponse(
            success=False,
            message="Cannot reset SYSTEM user password",
            errors=["Insufficient permissions"],
        )

    if data.new_password != data.confirm_new_password:
        return PasswordResponse(
            success=False,
            message="Passwords do not match",
            errors=["new_password and confirm_new_password must be identical"],
        )

    strength_errors = validate_password_strength(data.new_password)
    if strength_errors:
        return PasswordResponse(
            success=False,
            message="Password does not meet security requirements",
            errors=strength_errors,
        )

    target_user.password_hash = hash_password(data.new_password)
    db.commit()

    log_event(
        db, action="PASSWORD_RESET_BY_ADMIN", entity_type="user",
        entity_id=target_user.id, user_id=current_user.id,
        username=current_user.username,
        new_value={"target_user": target_user.username},
        ip_address=ip, user_agent=ua,
    )

    return PasswordResponse(
        success=True,
        message=f"Password reset successfully for user '{target_user.username}'",
    )

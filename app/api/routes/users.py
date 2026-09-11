"""User management API routes."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.dependencies import require_admin
from app.auth.password import hash_password
from app.auth.password_validation import validate_password_strength
from app.models.match import Match
from app.models.user import User, UserRole
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.services.audit import log_event, get_client_info

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    request: Request,
    data: UserCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new user. Requires ADMIN or SYSTEM role."""
    repo = UserRepository(db)
    existing = repo.get_by_username(data.username)
    if existing:
        raise HTTPException(status_code=409, detail=f"Username '{data.username}' already exists")
    if data.role == UserRole.SYSTEM:
        raise HTTPException(status_code=400, detail="Cannot create SYSTEM users via API")
    # Consistent with update/delete (review #6): only SYSTEM may extend the
    # ADMIN set. An ADMIN creating another ADMIN would be an unguarded role
    # grant where every other path to the ADMIN role is SYSTEM-only.
    if data.role == UserRole.ADMIN and current_user.role != UserRole.SYSTEM:
        raise HTTPException(
            status_code=403,
            detail="Only SYSTEM users can create ADMIN accounts",
        )
    strength_errors = validate_password_strength(data.password)
    if strength_errors:
        raise HTTPException(status_code=400, detail=strength_errors)
    # repo.create() flushes so user.id is assigned before the audit references
    # it. No commit yet: the user and its audit entry are committed together
    # below (Fix L7).
    user = repo.create(
        User(
            username=data.username,
            password_hash=hash_password(data.password),
            role=data.role,
            active=True,
        )
    )
    ip, ua = get_client_info(request)
    log_event(
        db,
        action="USER_CREATED",
        entity_type="user",
        entity_id=user.id,
        user_id=current_user.id,
        username=current_user.username,
        new_value={"username": user.username, "role": user.role.value},
        ip_address=ip,
        user_agent=ua,
    )
    db.commit()
    return user


@router.get("/", response_model=list[UserResponse])
def list_users(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """List all users. Requires ADMIN or SYSTEM role."""
    return UserRepository(db).get_all()


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int, current_user: User = Depends(require_admin), db: Session = Depends(get_db)
):
    """Get a user by ID. Requires ADMIN or SYSTEM role."""
    user = UserRepository(db).get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return user


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete a user account. Requires ADMIN or SYSTEM role.

    - SYSTEM users cannot be deleted.
    - Users cannot delete themselves.
    - ADMIN can only delete USER accounts.
    - SYSTEM can delete both ADMIN and USER accounts.
    """
    user = UserRepository(db).get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    # Cannot delete SYSTEM users
    if user.role == UserRole.SYSTEM:
        raise HTTPException(status_code=400, detail="Cannot delete SYSTEM user")

    # Cannot delete yourself
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    # ADMIN can only delete USER accounts, SYSTEM can delete both ADMIN and USER
    if current_user.role == UserRole.ADMIN and user.role == UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="ADMIN cannot delete other ADMIN accounts. Only SYSTEM can delete ADMIN accounts.",
        )

    # Cannot delete a user who authored matches: ``matches.created_by`` is a
    # FK to users.id (NOT NULL), so deleting the user would raise an unhandled
    # FK violation (Fix M4). Return a clear 400 pointing at the disable
    # workflow instead of a 500.
    authored_count = db.query(Match).filter(Match.created_by == user.id).count()
    if authored_count > 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"User '{user.username}' has authored {authored_count} match(es). "
                "Delete the matches first or disable the user account instead."
            ),
        )
    old_value = {"username": user.username, "role": user.role.value, "active": user.active}

    # Delete the user. No commit yet: the deletion and its audit entry are
    # committed together below (single transaction, Fix L7).
    UserRepository(db).delete(user)

    ip, ua = get_client_info(request)
    log_event(
        db,
        action="USER_DELETED",
        entity_type="user",
        entity_id=user_id,
        user_id=current_user.id,
        username=current_user.username,
        old_value=old_value,
        ip_address=ip,
        user_agent=ua,
    )
    db.commit()

    return {"message": f"User '{old_value['username']}' deleted successfully"}


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    request: Request,
    data: UserUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update a user. Requires ADMIN or SYSTEM role.

    Authorization model (mirrors ``delete_user``):
    - Only SYSTEM may modify the SYSTEM account or grant the SYSTEM role.
    - Only SYSTEM may modify ADMIN accounts.
    - A user can never change their own role or active state.
    """
    user = UserRepository(db).get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    # ── Authorization guards: prevent privilege escalation (review fix) ──
    # Without these checks an ADMIN could reset the SYSTEM account's password
    # or grant the SYSTEM role to any account - a full takeover. Mirrors the
    # delete_user hierarchy above.
    is_system = current_user.role == UserRole.SYSTEM

    # 1. Only SYSTEM may modify the SYSTEM account (password, role, active).
    if user.role == UserRole.SYSTEM and not is_system:
        raise HTTPException(
            status_code=403,
            detail="Only SYSTEM users can modify the SYSTEM account",
        )

    # 2. Only SYSTEM may grant the SYSTEM role.
    if data.role == UserRole.SYSTEM and not is_system:
        raise HTTPException(
            status_code=403,
            detail="Only SYSTEM users can grant the SYSTEM role",
        )

    # 2b. Only SYSTEM may grant the ADMIN role (closes the create/update gap
    # for the ADMIN set - review #6). Mirrors the create_user guard.
    if data.role == UserRole.ADMIN and not is_system:
        raise HTTPException(
            status_code=403,
            detail="Only SYSTEM users can grant the ADMIN role",
        )

    # 3. A user can never change their own role or active state.
    if user.id == current_user.id and (data.role is not None or data.active is not None):
        raise HTTPException(
            status_code=400,
            detail="You cannot change your own role or active state",
        )

    # 4. Only SYSTEM may modify an ADMIN account (same rule as delete_user).
    if user.role == UserRole.ADMIN and not is_system:
        raise HTTPException(
            status_code=403,
            detail="ADMIN cannot modify other ADMIN accounts. Only SYSTEM users can.",
        )

    # Defence in depth for the SYSTEM account (clearer 400s for SYSTEM edges).
    if user.role == UserRole.SYSTEM and data.role is not None and data.role != UserRole.SYSTEM:
        raise HTTPException(status_code=400, detail="Cannot downgrade SYSTEM user")
    if user.role == UserRole.SYSTEM and data.active is not None and not data.active:
        raise HTTPException(status_code=400, detail="Cannot disable SYSTEM user")

    old = {"role": user.role.value, "active": user.active}

    if data.password:
        strength_errors = validate_password_strength(data.password)
        if strength_errors:
            raise HTTPException(status_code=400, detail=strength_errors)
        user.password_hash = hash_password(data.password)
        # An admin-set password is a temporary reset: force a change on next login.
        user.must_change_password = True
    if data.role is not None:
        user.role = data.role
    if data.active is not None:
        user.active = data.active

    new = {"role": user.role.value, "active": user.active}

    action = "USER_UPDATED"
    if data.active is not None and not data.active:
        action = "USER_DISABLED"
    elif data.active is not None and data.active:
        action = "USER_ENABLED"
    if data.password:
        action = "PASSWORD_RESET"

    ip, ua = get_client_info(request)
    log_event(
        db,
        action=action,
        entity_type="user",
        entity_id=user.id,
        user_id=current_user.id,
        username=current_user.username,
        old_value=old,
        new_value=new,
        ip_address=ip,
        user_agent=ua,
    )
    # Single commit: the mutation and its audit entry are written together (Fix L7).
    db.commit()
    return user

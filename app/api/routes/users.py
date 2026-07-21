"""User management API routes."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.dependencies import require_admin
from app.auth.password import hash_password
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.services.audit import log_event, get_client_info

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(request: Request, data: UserCreate, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Create a new user. Requires ADMIN or SYSTEM role."""
    existing = db.query(User).filter(User.username == data.username).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Username '{data.username}' already exists")
    if data.role == UserRole.SYSTEM:
        raise HTTPException(status_code=400, detail="Cannot create SYSTEM users via API")
    user = User(username=data.username, password_hash=hash_password(data.password), role=data.role, active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    ip, ua = get_client_info(request)
    log_event(
        db, action="USER_CREATED", entity_type="user",
        entity_id=user.id, user_id=current_user.id, username=current_user.username,
        new_value={"username": user.username, "role": user.role.value},
        ip_address=ip, user_agent=ua,
    )
    return user


@router.get("/", response_model=list[UserResponse])
def list_users(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """List all users. Requires ADMIN or SYSTEM role."""
    return db.query(User).order_by(User.id).all()


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: int, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Get a user by ID. Requires ADMIN or SYSTEM role."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return user


@router.put("/{user_id}", response_model=UserResponse)
def update_user(user_id: int, request: Request, data: UserUpdate, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Update a user. Requires ADMIN or SYSTEM role."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    if user.role == UserRole.SYSTEM and data.role is not None and data.role != UserRole.SYSTEM:
        raise HTTPException(status_code=400, detail="Cannot downgrade SYSTEM user")
    if user.role == UserRole.SYSTEM and data.active is not None and not data.active:
        raise HTTPException(status_code=400, detail="Cannot disable SYSTEM user")

    old = {"role": user.role.value, "active": user.active}

    if data.password:
        user.password_hash = hash_password(data.password)
    if data.role is not None:
        user.role = data.role
    if data.active is not None:
        user.active = data.active
    db.commit()
    db.refresh(user)

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
        db, action=action, entity_type="user",
        entity_id=user.id, user_id=current_user.id, username=current_user.username,
        old_value=old, new_value=new,
        ip_address=ip, user_agent=ua,
    )
    return user
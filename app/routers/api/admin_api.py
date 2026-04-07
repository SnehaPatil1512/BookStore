"""Admin RBAC API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.dependencies import require_permission
from app.database import get_db
from app.models.permission import Permission
from app.models.role import Role
from app.models.user_model import User
from app.schemas.common_schema import MessageResponse
from app.schemas.rbac_schema import PermissionResponse, RoleResponse

router = APIRouter()


def _normalize_name(value: str) -> str:
    return value.strip()


def _get_role(db: Session, role_id: int) -> Role:
    role = db.query(Role).filter(Role.id == role_id).first()
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


def _get_permission(db: Session, permission_id: int) -> Permission:
    permission = db.query(Permission).filter(Permission.id == permission_id).first()
    if permission is None:
        raise HTTPException(status_code=404, detail="Permission not found")
    return permission


def _get_user(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/roles", response_model=RoleResponse)
def create_role(
    name: str = Query(..., min_length=1, max_length=64),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_permission("manage_users")),
) -> Role:
    """Create a new role by name."""
    role_name = _normalize_name(name)
    if not role_name:
        raise HTTPException(status_code=400, detail="Role name is required")

    existing = db.query(Role).filter(Role.name == role_name).first()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Role already exists")

    role = Role(name=role_name)
    db.add(role)
    try:
        db.commit()
        db.refresh(role)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not create role")
    return role


@router.post("/permissions", response_model=PermissionResponse)
def create_permission(
    name: str = Query(..., min_length=1, max_length=64),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_permission("manage_users")),
) -> Permission:
    """Create a new permission by name."""
    permission_name = _normalize_name(name)
    if not permission_name:
        raise HTTPException(status_code=400, detail="Permission name is required")

    existing = db.query(Permission).filter(Permission.name == permission_name).first()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Permission already exists")

    permission = Permission(name=permission_name)
    db.add(permission)
    try:
        db.commit()
        db.refresh(permission)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not create permission")
    return permission


@router.post("/roles/{role_id}/permissions/{permission_id}", response_model=MessageResponse)
def assign_permission(
    role_id: int,
    permission_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_permission("manage_users")),
) -> MessageResponse:
    """Assign a permission to a role."""
    role = _get_role(db, role_id)
    permission = _get_permission(db, permission_id)

    if permission not in role.permissions:
        role.permissions.append(permission)

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not assign permission")

    return MessageResponse(message="Permission assigned")


@router.post("/users/{user_id}/roles/{role_id}", response_model=MessageResponse)
def assign_role(
    user_id: int,
    role_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_permission("manage_users")),
) -> MessageResponse:
    """Assign a role to a user."""
    user = _get_user(db, user_id)
    role = _get_role(db, role_id)

    user.roles = [role]
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not assign role")

    return MessageResponse(message="Role assigned")


@router.get("/users/{user_id}/permissions", response_model=list[str])
def get_user_permissions(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_permission("manage_users")),
) -> list[str]:
    """Return flattened permission list for a user."""
    user = _get_user(db, user_id)
    return user.permission_names


@router.get("/dashboard", response_model=MessageResponse)
def admin_dashboard(
    user: User = Depends(require_permission("manage_users")),
) -> MessageResponse:
    """Health-check style admin endpoint."""
    return MessageResponse(message=f"Welcome, {user.username}")

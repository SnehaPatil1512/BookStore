"""Permission persistence helpers."""

from sqlalchemy.orm import Session, selectinload

from app.models.permission import Permission
from app.models.role import Role


def get_all_permissions(db: Session) -> list[Permission]:
    """List all permissions with linked roles."""
    return (
        db.query(Permission)
        .options(selectinload(Permission.roles))
        .order_by(Permission.name)
        .all()
    )


def get_permission_by_name(db: Session, name: str) -> Permission | None:
    """Fetch permission by name."""
    return db.query(Permission).filter(Permission.name == name).first()


def get_permission_by_id(db: Session, permission_id: int) -> Permission | None:
    """Fetch permission by id."""
    return db.query(Permission).filter(Permission.id == permission_id).first()


def get_roles_by_names(db: Session, role_names: list[str]) -> list[Role]:
    """Resolve role entities by role names list."""
    if not role_names:
        return []

    return (
        db.query(Role)
        .filter(Role.name.in_(role_names))
        .order_by(Role.name)
        .all()
    )


def create_permission(
    db: Session,
    *,
    name: str,
    role_names: list[str] | None = None,
) -> Permission:
    """Create permission and optionally assign roles."""
    permission = Permission(name=name)
    if role_names is not None:
        permission.roles = get_roles_by_names(db, role_names)
    db.add(permission)
    db.commit()
    db.refresh(permission)
    return permission


def update_permission_roles(
    db: Session,
    *,
    permission: Permission,
    role_names: list[str],
) -> Permission:
    """Replace role assignments for a permission."""
    permission.roles = get_roles_by_names(db, role_names)
    db.commit()
    db.refresh(permission)
    return permission


def delete_permission(db: Session, *, permission: Permission) -> None:
    """Delete permission and clear associations."""
    permission.roles = []
    db.flush()
    db.delete(permission)
    db.commit()

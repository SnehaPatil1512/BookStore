"""Seed baseline RBAC roles and permissions."""

from sqlalchemy.orm import Session

from app.models.permission import Permission
from app.models.role import Role


def seed_rbac(db: Session) -> None:
    """Create default roles/permissions and attach mappings."""
    role_permissions = {
        "admin": [
            "view_book",
            "create_book",
            "update_book",
            "delete_book",
            "manage_users",
            "manage_books",
        ],
        "editor": [
            "view_book",
            "create_book",
            "update_book",
            "delete_book",
        ],
        "viewer": [
            "view_book",
        ],
    }

    permission_lookup = {
        permission.name: permission
        for permission in db.query(Permission).all()
    }

    for permission_name in sorted({
        permission_name
        for permission_names in role_permissions.values()
        for permission_name in permission_names
    }):
        if permission_name not in permission_lookup:
            permission = Permission(name=permission_name)
            db.add(permission)
            permission_lookup[permission_name] = permission

    db.flush()

    role_lookup = {
        role.name: role
        for role in db.query(Role).all()
    }

    for role_name, permission_names in role_permissions.items():
        role = role_lookup.get(role_name)
        if role is None:
            role = Role(name=role_name)
            db.add(role)
            role_lookup[role_name] = role

        role.permissions = [permission_lookup[name] for name in permission_names]

    db.commit()

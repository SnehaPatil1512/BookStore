"""Association tables for user-role and role-permission links."""

from sqlalchemy import Column, ForeignKey, Integer

from app.database import Base


class UserRole(Base):
    """Join table linking users and roles."""

    __tablename__ = "user_roles"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id"), primary_key=True)


class RolePermission(Base):
    """Join table linking roles and permissions."""

    __tablename__ = "role_permissions"

    role_id = Column(Integer, ForeignKey("roles.id"), primary_key=True)
    permission_id = Column(Integer, ForeignKey("permissions.id"), primary_key=True)

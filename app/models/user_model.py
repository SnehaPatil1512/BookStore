"""SQLAlchemy user model."""

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    """Application user with RBAC roles."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True)
    email = Column(String, unique=True)
    hashed_password = Column(String)
    books = relationship("Book", back_populates="owner")
    roles = relationship("Role", secondary="user_roles", back_populates="users")

    @property
    def role_names(self) -> list[str]:
        return [role.name for role in self.roles]

    @property
    def permission_names(self) -> list[str]:
        permissions = {
            permission.name
            for role in self.roles
            for permission in role.permissions
        }
        return sorted(permissions)

    @property
    def is_admin(self) -> bool:
        return "admin" in self.role_names

    def has_permission(self, permission_name: str) -> bool:
        return any(
            permission.name == permission_name
            for role in self.roles
            for permission in role.permissions
        )

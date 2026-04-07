"""SQLAlchemy permission model."""

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Permission(Base):
    """Permission entity assignable to roles."""

    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)

    roles = relationship("Role", secondary="role_permissions", back_populates="permissions")

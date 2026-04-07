"""Schemas for role and permission API responses."""

from pydantic import BaseModel, ConfigDict


class RoleResponse(BaseModel):
    """Role representation."""

    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class PermissionResponse(BaseModel):
    """Permission representation."""

    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)
